# AUTOGENERATED! DO NOT EDIT! File to edit: 03_auto_augment.ipynb (unless otherwise specified).

__all__ = ['device', 'fastai2pil_basis', 'pil2fastai_basis', 'pil2tensor', 'flip_horizontal', 'flip_vertical',
           'swap_xy_coords', 'rotate_bb', 'shear_x_bboxes', 'rotate_bboxes', 'ImageNetPolicy', 'SubPolicy']

# Cell
#from fastai.vision.all import *
from fastai import *
import numpy as np

from torch import tensor, Tensor
import torch

# For use in Auto Augment data transformations
import random
import torchvision.transforms.functional as FT
from typing import *
from PIL import Image, ImageEnhance, ImageOps
import math
import copy

# Cell
# Automatically sets for GPU or CPU environments
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Cell
# Convert FASTAI image basis. (-1,-1) top-left (1,1) bottom-right  to PIL image basis (0,0) top-left to (1,1) bottom-right
def fastai2pil_basis(b) :  return ((b + 1.)).div(2.)      # b - Bounding box(s)

# Cell
# Convert PIL image basis (0,0) top-left to (1,1) bottom-right  to FASTAI image basis. (-1,-1) top-left to (1,1) bottom-right
def pil2fastai_basis(b):  return (b * 2.).float() - 1.    # b - Bounding box(s)

# Cell
# Helper Function
def pil2tensor(image:Image,dtype:np.dtype)->Tensor:
    ''' Convert PIL style `image` array to torch style image tensor.
        Imput -  image -image in PILImage form
        output - image in FASTAI image format
        '''
    a = np.asarray(image)
    if a.ndim==2 : a = np.expand_dims(a,2)
    a = np.transpose(a, (1, 0, 2))
    a = np.transpose(a, (2, 1, 0))
    return torch.from_numpy(a.astype(dtype, copy=False) )

# Cell
def flip_horizontal(bboxes):
  '''
    Flips a bounding box tensor along the vertical axis
    Input:    bboxes - 2-d tensor containing bounding boxes in the format x1y1x2y2
    Output:   Bounding boxes flipped along the vertical axis in the format x1y1x2y2
  '''
  bboxes[...,[0,2]] = torch.flip(bboxes[...,[0,2]], [len(bboxes.size())-1]) * -1.     # Swap the (x) columns: 0, and 2 and change sign                                                     # Flip the sign of each of these columns
  return bboxes

# Cell
def flip_vertical(bboxes):
  '''
    Flips a bounding box tensor along the horizontal axis
    Input:    bboxes - 2-d tensor containing bounding boxes in the format x1y1x2y2
    Output:   Bounding boxes flipped along the horizontal axis in the format x1y1x2y2
  '''
  bboxes[...,[1,3]] = torch.flip(bboxes[...,[1,3]], [len(bboxes.size())-1]) * -1.     # Swap the (x) columns: 0, and 2 and change sign
  return bboxes

# Cell
def swap_xy_coords (bboxes):
  ''' swap yx coordinate sequences in bounding boxes into xy sequences, and viceversa
      Input:    bboxes - 2-d tensor containing bounding boxes
      Output:   Bounding boxes flipped with swapped coordinate, xy --> yx
  '''
  bboxes[...,[0,1]] = torch.flip(bboxes[...,[0,1]], [len(bboxes.size())-1])
  bboxes[...,[2,3]] = torch.flip(bboxes[...,[2,3]], [len(bboxes.size())-1])
  return bboxes

# Cell
def rotate_bb(bb:Tensor, rads:float):
    ''' Rotate a bounding box (x1,y1,x2,y2) by an angle
        Input:  bb -   bounding box  (needs to be off-cuda)
                rads - rotation angle in radians
    '''
    M = torch.tensor([                         # Rotation Matrix
           [math.cos(rads), -math.sin(rads)],
           [math.sin(rads),  math.cos(rads)]
           ] ).to(device)
    #return torch.mm(bb,M)
    return torch.matmul(bb,M)


# Cell
# SHEAR-HORIZONTALLY BOUNDING BOXES
def shear_x_bboxes (bboxes:Tensor, factor:float, y_first=True):
  '''
    Shear horizontally a tensor of bounding boxes
    Input:
          bboxes  -      2-d tensor of bounding boxes associated with the image
          factor  -      Factor by which the image in sheared in the horizontal direction
          y_first -      Input coordinates in the format y1x1y2x2
          TODO: change this
    Output:
          bboxes -       Sheared bounding boxes
  '''
  if not y_first: swap_xy_coords(bboxes)                                # swap yx sequence for xy sequence
  m = bboxes[(bboxes == 0.).all(1)]                                     # Retain the all-zero rows
  bboxes = bboxes[~(bboxes == 0.).all(1)]                               # Retain the non all-zero rows
  mag = factor                                                          # If the factor is negative, flip the boxes about the (0,0) center
  if factor <= 0 : mag = -factor; bboxes = flip_horizontal(bboxes)      # so it can be sheared correctly (in the positive orientation)
  bboxes = fastai2pil_basis(bboxes)                                     # Convert to PIL image basis (0,0) to (1,1)
  bboxes[:,[1,3]] = bboxes[:,[1,3]] + bboxes[:,[0,2]]  * mag            # Shear in the horizontal direction (to the right)
  bboxes = pil2fastai_basis(bboxes)                                     # Convert to FASTAI image basis. Top-left (-1,-1) to Bottom-right (1,1)
  if factor <= 0 : bboxes = flip_horizontal(bboxes)                     # If factor is negative, restore the boxes to the original orientation
  bboxes = torch.clamp(bboxes, -1, 1)                                   # Clamp coordinates to [-1, 1]
  bboxes = torch.cat([m, bboxes], dim=0)                                # Graft the all-zero rows back to the bounding box array
  if not y_first: swap_xy_coords(bboxes)                                # restore xy sequence
  return bboxes


# Cell
# ROTATE BOUNDING BOXES
def rotate_bboxes(bboxes:Tensor, degrees:float):
  '''
    Rotate bounding boxes (in sync with a rotated image)
    Input:
        bboxes :       tensor of bounding boxes in the format x1,y1,x2,y2
        degrees :      Angle in degrees to rotate the box as float
    Output:
        bboxes         tensor of rotated bounding boxes
  '''
  rads = math.radians(degrees)                                          # Convert degrees to radians
  p =len(bboxes.shape)-1                                                # nNmber of dimensions in bboxes
  m = bboxes[(bboxes == 0.).all(p)]                                     # Retain the all-zero rows of the bounding box
  bboxes = bboxes[~(bboxes == 0.).all(p)]                               # Retain the non all-zero rows of the bounding box
  lgt = abs(bboxes[...,[0]] - bboxes[...,[2]])                          # Calculate the length of the box in the x axis
  mag = rads                                                            # If degrees is negative, flip the boxes about the (0,0) center
  if degrees <= 0 : mag = -rads; bboxes = flip_horizontal(bboxes)       # so it can be rotated correctly (in the positive orientation)
  bboxes = bboxes.reshape(-1,2)                                         # Put tensor into a (n x 2) vertical array
  bboxes = rotate_bb(bboxes, mag)                                       # Rotate the bounding box by the magnitude given
  bboxes = bboxes.reshape(-1,4)                                         # Restore coordinates to fastai image basis
  bboxes [...,[1]] = bboxes [...,[1]] - (lgt)*math.sin(mag)             # Calculate the delta-lenght to add and substract to
  bboxes [...,[3]] = bboxes [...,[3]] + (lgt)*math.sin(mag)             #   the y coordinates to compensate for the rotation
  if degrees <= 0 : bboxes = flip_horizontal(bboxes)                    # If degrees is negative, restore the boxes to the original orientation
  bboxes = torch.clamp(bboxes, -1, 1)                                   # Clamp coordinates to [-1, 1]

  return torch.cat([m, bboxes], dim=0)                         # Graft the all-zero rows back to the bounding box and return


# Cell
class ImageNetPolicy():
    '''
    Augmentation policy for the ImageNet Dataset.
    (As per the paper Learning Data Augmentation Strategies for Object detection. Barret Zoph, et. al. 6/26/2019)
    The Policy is composed of a series of sub-policies.
    Each sub-policy contains two (2) augmentation steps. i. e. 'posterize', 'rotate'
    Each step consists of:
          (1) an operation i.e. 'posterize',
          (2) probability of application. i.e. 0.4, and
          (3) magnitude indicating the intensity of the operation.i.e 8
    Author:  J. Adolfo Villalobos @ 2020
    '''
    def __init__(self, fillcolor=(128, 128, 128)):

        self.policy = [
            SubPolicy("posterize", 0.4, 8, "rotate",       0.6, 9, fillcolor),
            SubPolicy("solarize",  0.6, 5, "autocontrast", 0.6, 5, fillcolor),
            SubPolicy("equalize",  0.8, 8, "equalize",     0.6, 3, fillcolor),
            SubPolicy("posterize", 0.6, 7,"posterize",     0.6, 6, fillcolor),
            SubPolicy("equalize",  0.4, 7,"solarize",      0.2, 4, fillcolor),

            SubPolicy("equalize",  0.4, 4, "rotate",       0.8, 8, fillcolor),
            SubPolicy("solarize",  0.6, 3, "equalize",     0.6, 7, fillcolor),
            SubPolicy("posterize", 0.8, 5, "equalize",     1.0, 2, fillcolor),
            SubPolicy("rotate",    0.2, 3, "solarize",     0.6, 8, fillcolor),
            SubPolicy("equalize",  0.6, 8, "posterize",    0.4, 6, fillcolor),

            SubPolicy("rotate",    0.8, 8, "color",        0.4, 0, fillcolor),
            SubPolicy("rotate",    0.4, 9, "equalize",     0.6, 2, fillcolor),
            SubPolicy("equalize",  0.0, 7, "equalize",     0.8, 8, fillcolor),
            SubPolicy("invert",    0.6, 4, "equalize",     1.0, 8, fillcolor),
            SubPolicy("color",     0.6, 4, "contrast",     1.0, 8, fillcolor),

            SubPolicy("rotate",    0.8, 8, "color",        1.0, 2, fillcolor),
            SubPolicy("color",     0.8, 8, "solarize",     0.8, 7, fillcolor),
            SubPolicy("sharpness", 0.4, 7, "invert",       0.6, 8, fillcolor),
            SubPolicy("shearX",    0.6, 5, "equalize",     1.0, 9, fillcolor),
            SubPolicy("color",     0.4, 0, "equalize",     0.6, 3, fillcolor),

            SubPolicy("equalize",  0.4, 7, "solarize",     0.2, 4, fillcolor),
            SubPolicy("solarize",  0.6, 5, "autocontrast", 0.6, 5, fillcolor),
            SubPolicy("invert",    0.6, 4, "equalize",     1.0, 8, fillcolor),
            SubPolicy("color",     0.6, 4, "contrast",     1.0, 8, fillcolor),
            SubPolicy("equalize",  0.8, 8, "equalize",     0.6, 3, fillcolor)
        ]


    def __call__(self, x, y):
      '''Fetch a random sub-policy'''
      policy_idx = random.randint(0, len(self.policy) - 1)
      return self.policy[policy_idx](x, y)

    def __repr__(self):
        return "AutoAugment Policy for the ImageNet Dataset. "

# Cell
class SubPolicy():
    def __init__(self, operation1, p1, magnitude_idx1, operation2, p2, magnitude_idx2, fillcolor=(128, 128, 128)):
        '''
        The magnitude that is specified for each subpolicy item is a number from 1 to 10.
        This number translates to a separate measure which varies for each operation. The specific measure
        is picked up from a range of uniformly spaced physical attribute values according to the dictionary below.
        '''
        ranges = {
            "shearX": np.linspace(-0.3, 0.3, 10),
            "shearY": np.linspace(-0.3, 0.3, 10),
            "translateX": np.linspace(-150, 150 / 331, 10),
            "rotate": np.linspace(-30, 30, 10),
            "color": np.linspace(0.1, 1.9, 10),
            "posterize": np.round(np.linspace(8, 4, 10), 0).astype(np.int),
            "solarize": np.linspace(256, 0, 10),
            "contrast": np.linspace(0.1, 1.9, 10),
            "sharpness": np.linspace(0.1, 1.9, 10),
            "brightness": np.linspace(0.1, 1.9, 10),
            "autocontrast": [0] * 10,
            "equalize": [0] * 10,
            "invert": [0] * 10
        }

        # Custom rotate with fill
        def rotate_with_fill(img:PILImage, yb, mag):
            ob = rotate_bboxes(yb, mag, y_first=False)
            return [img.convert("RGBA").rotate(mag, resample=Image.BICUBIC, fillcolor=(128,128,128)).convert(img.mode), ob]    # Rotate the image

        # Shear horizontal
        def shear_horizontal (img:PILImage, yb, mag):
            trb = mag*random.choice([-1, 1])
            tri = (1, -trb, 0, 0, 1, 0)
            b_tf = img.transform(img.size, Image.AFFINE, tri, Image.BICUBIC,fillcolor=(128,128,128) )
            ob = shear_x_bboxes (yb, trb, y_first=False)
            return [b_tf, ob]

        # Transform functions
        func = {

            "rotate": lambda img, yp, magnitude: rotate_with_fill(img, yp, magnitude),
            "shearX": lambda img, yp, magnitude: shear_horizontal(img, yp, magnitude),
            "color": lambda img, yp, magnitude: [ImageEnhance.Color(img).enhance(magnitude), yp],
            "posterize": lambda img, yp, magnitude: [ImageOps.posterize(img, magnitude), yp],
            "solarize": lambda img, yp, magnitude: [ImageOps.solarize(img, magnitude), yp],
            "contrast": lambda img, yp, magnitude: [ImageEnhance.Contrast(img).enhance(
                1 + magnitude * random.choice([-1, 1])), yp],
            "sharpness": lambda img, yp, magnitude: [ImageEnhance.Sharpness(img).enhance(
                1 + magnitude * random.choice([-1, 1])), yp],
            "brightness": lambda img, yp, magnitude: [ImageEnhance.Brightness(img).enhance(
                1 + magnitude * random.choice([-1, 1])), yp],
            "autocontrast": lambda img, yp, magnitude: [ImageOps.autocontrast(img), yp],
            "equalize": lambda img, yp, magnitude: [ImageOps.equalize(img, mask=None), yp],
            "invert": lambda img, yp, magnitude: [ImageOps.invert(img), yp]
        }

        # Probabilities
        self.p1 = p1; self.p2 = p2

        #  Fetch a Fastai transform corresponding to the given subpolicy step operation
        self.operation1 = func[operation1]; self.operation2 = func[operation2]
        self.magnitude1 = ranges[operation1][magnitude_idx1]; self.magnitude2 = ranges[operation2][magnitude_idx2]

    # Randomized filtering
    def __call__(self, x, y):
        # Transfor image tensor to PIL image
        img = FT.to_pil_image(x.data.cpu(), mode='RGB')
        # Fetch a Fastai-formatted transform corresponnding to the given Subpolicy
        if random.random() < self.p1: img, y = self.operation1(img, y, self.magnitude1)
        if random.random() < self.p2: img, y = self.operation2(img, y, self.magnitude2)
        # Revert to FASTAI Image format
        img = pil2tensor(img, dtype=np.float32) #.div(255)
        return img, y      # returns the transformed image and corresponding bounding boxes