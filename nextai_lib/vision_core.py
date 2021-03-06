# AUTOGENERATED! DO NOT EDIT! File to edit: 00_vision_core.ipynb (unless otherwise specified).

__all__ = ['device', 'ctrhw2tlbr', 'tlbr2cthw', 'activ_decode', 'activ_encode', 'strip_zero_rows',
           'graft_zerorows_to_tensor', 'flip_on_y_axis', 'flip_on_x_axis', 'rotate_90_plus', 'rotate_90_minus']

# Cell
from fastai.imports import *
from torch import tensor, Tensor
import torch

# Cell
# Automatically sets for GPU or CPU environments
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Cell
# Helper Functions for Predictor Methods
def ctrhw2tlbr(boxes:Tensor, set_if_input_is_CxCyWH=False):
  ''' Convert bounding box coordinates from CTRHW to x1, y1, x2, y2 formats
      IMPORTANT: The method expects the input box tensor to be in CxCyHW.
      Inputs:
          Boxes        - torch.tensor of activation bounding boxes
          Dim  -         (batch size x Items in batch x 4). It will fail otherwise.
          Input Format - Center coord, height, width

      Output:
          torch.tensor of activation bounding boxes
          Dim = (batch size, Items in batch, 4)
          Format: x1, y1, x2, y2
          '''
  if set_if_input_is_CxCyWH: boxes = boxes[:,:,[0,1,3,2]]                    # Adjust the format to CxCyHW (height, width). This is the FASTAI format

  x1 = (boxes[:,:,0] - torch.true_divide(boxes[:,:,3],2.)).view(-1,1)
  x2 = (boxes[:,:,0] + torch.true_divide(boxes[:,:,3],2.)).view(-1,1)
  y1 = (boxes[:,:,1] - torch.true_divide(boxes[:,:,2],2.)).view(-1,1)
  y2 = (boxes[:,:,1] + torch.true_divide(boxes[:,:,2],2.)).view(-1,1)

  return torch.cat([x1,y1,x2,y2],dim=1)

# Cell
def tlbr2cthw(boxes:Tensor, ctrhw=True):
  '''Convert top/left bottom/right format `boxes` to center/size corners.
      Input:
          boxes - torch.Tensor of activations bounding boxes
                  Unbounded
                  Dim = (batch size, Items in batch, 4)
                  Format: top left xy, bottom right xy
          ctrhw =  True -  Output is in the format CxCyHW
                   False - Output is in the format CxCyWH
      Output:
                  torch.tensor of activation bounding boxes
                  Dim = (batch size, Items in the batch, 4)
                  Format: center coord xy, height, width'''
  center = torch.true_divide(boxes[:,:, :2] + boxes[:,:, 2:], 2)                     # Calculate box center coord
  sizes = torch.abs(boxes[:,:, 2:] - boxes[:,:, :2])                # Calculate box width & height                                         #
  results = torch.cat( (center, sizes), 2)
  if ctrhw: results = results[:,:,[0,1,3,2]]                        # The correct FASTAI Size format is CxCyHW (height, width)

  return results

# Cell
# We apply Decoding With Variance to both activation boxes and anchor boxes to calculate the final bounding boxes.
def activ_decode(p_boxes:Tensor, anchors:Tensor):
  ''' Decodes box activations into final bounding boxes by calculating predicted anchor offsets, which are then added to anchor boxes
        Input:
            p_boxes - torcht.tensor of activation bounding boxes
                      dim:       (batch, items in batch, 4)
                      Format:     top left xy, bottom right xy
            anchors - torch.tensor of anchors
                      Dim:       (k * no of classes) x 4
                      Format:    CxCyWH format
        Output:
                      torcht.tensor with anchor boxes offset by box activations
                      dim:    batch x tems in batch x 4)
                      Format: tlbr - top left xy, bottom right xy'''

  sigma_xy, sigma_hw = torch.sqrt(torch.tensor([0.1])), torch.sqrt(torch.tensor([0.2]))             # Variances for center and hw coordinates

  pb = torch.tanh( p_boxes)                 # Set activations into [-1,1] basis (as used in Fastai)

  ctrwh = tlbr2cthw(pb, ctrhw=False)        # Transform box activations from xyxy format to CxCyWH format.

  # Calculate offset centers. The sequence is Xp, followed by Yp
  offset_centers = ctrwh[:,:,[0,1]].to(device) * sigma_xy.to(device) * anchors[:,[2,3]].to(device) + anchors[:,[0,1]].to(device)

  # Calculate offset sizes. The sequence is Wp, followed by Hp
  offset_sizes =  torch.exp(ctrwh[:,:,[2,3]].to(device) *sigma_hw.to(device)) *anchors[:,[2,3]].to(device)

  # Return format to CxCyHW and then return, switching back to X1Y1X2Y2 format.
  return torch.clamp(ctrhw2tlbr(torch.cat([offset_centers, offset_sizes], 2), set_if_input_is_CxCyWH=True).view(*p_boxes.shape), min=-1, max=+1)

# Cell
# Transform activations into final bounding boxes by calculating the predicted offsets to the anchor boxes
def activ_encode(p_boxes:Tensor, anchors:Tensor):
  ''' Transforms activations into final bounding boxes by calculating predicted anchor offsets, which are then added to the anchor boxes
        Input:
            p_boxes - torcht.tensor of activation bounding boxes
                      dim:    (batch, items in batch, 4)
                      Format: top left xy, bottom right xy
        Output:
                      torch.tensor
  '''
  sigma_ctr, sigma_hw = torch.sqrt(torch.tensor([0.1])), torch.sqrt(torch.tensor([0.2]))         # Variances
  pb = torch.tanh( p_boxes)                 # Set activations into the basis [-1,1] (as used in Fastai)  pb = torch.tanh(p_boxes[...,:] )
  to_ctrwh = tlbr2cthw(pb, tlbr=False)      # Transform activaions from xyxy format to ctrwh format. This will facilitate offset calculations below

  # Calculate anchors with offsets to serve as predicted bounded boxes
  offset_center = sigma_ctr * (to_ctrwh[:,:,[0,1]].to(device) - anchors[:,[0,1]].to(device)) / anchors[:,[2,3]].to(device)
  offset_size = torch.log(to_ctrwh[:,:,[2,3]].to(device)/anchors[:,[2,3]].to(device)) / sigma_hw
  centers = anchors[:,[0,1]].to(device) + offset_center.to(device)
  sizes =   anchors[:,[2,3]].to(device) + offset_size.to(device)

  return cthw2corners(torch.cat([centers, sizes], 2))

# Cell
# Strip zero-valued rows from a bounding box tensor
def strip_zero_rows(bboxes:Tensor):
  ''' Strip zero-valued rows from a bounding box tensor
      Input:  bboxes   Bounding boox tensor
      Output: b_out    Tensor with data rows
              z_out    Tensor with zero-filled rows '''
  b_out = []; z_out = []

  for rw in torch.arange(bboxes.shape[0]):
      cc = bboxes[rw,0:][~(bboxes[rw,0:] == 0.).all(1)]                               # Retain the non all-zero rows of the bounding box
      if cc.nelement() != 0 : b_out.append(cc)
      zz = bboxes[rw,0:][(bboxes[rw,0:] == 0.).all(1)]                                # Retain the all-zero rows of the bounding box
      if cc.nelement() == 0 : z_out.append(zz)

  #return (b_out, z_out)
  return (torch.stack(b_out), torch.stack(z_out))

# Cell
# Graft the all-zero rows back to the bounding box array
def graft_zerorows_to_tensor(bboxes:Tensor, zboxes:Tensor):
  ''' Graft the all-zero rows back to the bounding box row(s)
      Input   bboxes   Bounding boox tensor
              zboxes   Tensor containing the zero-valued rows stripped by strip_zero_rows function
      Output  Tensor with data and zero-filled rows of shape[0] = shape bboxes[0} shape.zeroboxes[0]'''

  return torch.cat([bboxes, zboxes], dim=1)

# Cell
# Flip a bounding box along the y axis
def flip_on_y_axis(bboxes:Tensor):
    ''' Flip a bounding box along the y axis
        Input:   bboxes   Bounding box tensor '''
    return bboxes[...,[2,1,0,3]]*torch.tensor([-1.,1.,-1.,1.])

# Cell
# Flip a bounding box along the x axis
def flip_on_x_axis(bboxes:Tensor):
    ''' Flip a bounding box along the x axis
        Input:   bboxes   Bounding boox tensor '''
    return bboxes[...,[0,3,2,1]]*torch.tensor([1.,-1.,1.,-1.])

# Cell
def rotate_90_plus(bb:Tensor):
  ''' Rotate bounding box(s) by 90 degrees clockwise
      Input:   bboxes   Bounding boox tensor '''
  return bb[...,[3,0,1,2]]*torch.tensor([-1.,1.,-1.,1.])

# Cell
def rotate_90_minus(bb:Tensor):
  ''' Rotate bounding box(s) by 90 degrees counterclockwise
      Input:   bboxes   Bounding boox tensor in xyxy format'''
  return bb[...,[1,2,3,0]]*torch.tensor([1.,-1.,1.,-1.])