# AUTOGENERATED! DO NOT EDIT! File to edit: 02_inference.ipynb (unless otherwise specified).

__all__ = ['device', 'pad_output', 'get_activ_offsets_mns']

# Cell
from fastai.vision.all import *
from typing import *
from torch import tensor, Tensor
import torch
import torchvision      # Needed to invoke torchvision.ops.mns function

# Cell
from vision_core import *
#from anchor_boxes import *

# Cell
# Automatically sets for GPU or CPU environments
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Cell
# Pad tensors so that they have uniform dimentions: (batch size, no of items in a batch, 4) and  (batch size, no of items in a batch, 21)
def pad_output(l_bb:List, l_scr:List, l_idx:List, no_classes:Int):
  '''Pad tensors so that they have uniform dimentions: (batch size, no of items in a batch, 4) and  (batch size, no of items in a batch, 21)
      Inputs: l_bb  - list  of tensors containing individual non-uniform sized bounding boxes
              l_scr - list  of tensors containing class index values (i.e. 1 - airplane)
              l_idx - list of tensors containing class index values (i.e. 1 - airplane)
              no_classes - Number of classes, Integer
      Outputs: Uniform-sized tensors: bounding box tensor and score tensor with dims: (batch size, no of items in a batch, 4) and  (batch size, no of items in a batch, 21)'''

  if len([len(img_bb) for img_bb in l_bb]) == 0.:
    print(F'Image did not pass the scoring threshold')
    return

  mx_len = max([len(img_bb) for img_bb in l_bb])                  # Calculate maximun lenght of the boxes in the batch

  l_b, l_c, l_x, l_cat = [], [], [], []
  # Create Bounding Box tensors                                      # zeroed tensor accumulators
  for i, ntr in enumerate(zip(l_bb, l_scr, l_idx)):
    bbox, cls, idx = ntr[0], ntr[1], ntr[2]                     # Unpack variables
    tsr_len = mx_len - bbox.shape[0]                            # Calculate the number of zero-based rows to add
    m = nn.ConstantPad2d((0, 0, 0, tsr_len), 0.)                # Prepare to pad the box tensor with zero entries
    l_b.append(m(bbox))                                         # Add appropriate zero-based box rows and add to list

    # Create Category tensors
    cat_base = torch.zeros(mx_len-bbox.shape[0], dtype=torch.int32)
    img_cat = torch.cat((idx, cat_base), dim=0)
    l_cat.append(img_cat)

    # Create Score tensors
    img_cls = []                                                # List to construct class vectors
    for ix in range(idx.shape[0]):                              # Construct class vectors of dim(no of classes)
        cls_base = torch.zeros(no_classes).to(device)           # Base zero-based class vector
        cls_base[idx[ix]] = cls[ix]                             # Add the score in the nth position
        img_cls.append(cls_base)
    img_stack = torch.stack(img_cls)                            # Create single tensor per image
    img_stack_out =  m(img_stack)
    l_c.append( img_stack_out )                                 # Add appropriate zero-based class rows and add to list

  return (TensorBBox(torch.stack(l_b,0)), TensorMultiCategory(torch.stack(l_c,0)), TensorMultiCategory(torch.stack(l_cat,0)) )

# Cell
def get_activ_offsets_mns(anchrs:Tensor, activs:Tensor, no_classes:Int, threshold:Float=0.5):
  ''' Takes in activations and calculates corresponding anchor box offsets.
      It then filters the resulting boxes through MNS
      Inputs:
          anchrs - Anchors as Tensor
          activs - Activations as Tensor
          no_classes - Number of classes (categories)
          threshold - Coarse filtering. Default = 0.5
      Output:
          one_batch_boxes, one_batch_scores as Tuple'''

  p_bboxes, p_classes = activs    # Read p_bboxes: [32, 189,4] Torch.Tensor and  p_classes: [32, 189, 21]  Torch.Tensor from self.learn.pred

  #scores = torch.sigmoid(p_classes)                    # Calculate the confidence levels, scores, for class predictions [0, 1]
  scores = torch.softmax(p_classes, -1)                  # Calculate the confidence levels, scores, for class predictions [0, 1] - Probabilistic

  offset_boxes = activ_decode(p_bboxes, anchrs)    # Return anchors + anchor offsets wiith format (batch, No Items in Batch, 4)

  # For each item in batch, and for each class in the item, filter the image by passing it through NMS. Keep preds with IOU > thresshold
  one_batch_boxes = []; one_batch_scores = []; one_batch_cls_pred = []  # Agregators at the bath level

  for i in range(p_classes.shape[0]):                   # For each image in batch ...
    batch_p_boxes = offset_boxes[i]                     # box preds for the current batch
    batch_scores = scores[i]                            # Keep scores for the current batch
    max_scores, cls_idx = torch.max(batch_scores, 1 )   # Keep batch class indexes
    bch_th_mask = max_scores > threshold           # Threshold mask for batch
    bch_keep_boxes = batch_p_boxes[bch_th_mask]         #  "
    bch_keep_scores = batch_scores[bch_th_mask]         #  "
    bch_keep_cls_idx = cls_idx[bch_th_mask]

    # Agregators per image in a batch
    img_boxes = []                                      # Bounding boxes per image
    img_scores = []                                     # Scores per image
    img_cls_pred = []                                   # Class predictons per image

    for c in range (1,no_classes):                      # Loop through each class

      cls_mask = bch_keep_cls_idx==c                    # Keep masks for the current class
      if cls_mask.sum() == 0: continue                  # Weed out images with no positive class masks

      cls_boxes = bch_keep_boxes[cls_mask]              # Keep boxes per image
      cls_scores = bch_keep_scores[cls_mask].max(dim=1)[0]    # Keep class scores for the current image

      nms_keep_idx = torchvision.ops.nms(cls_boxes, cls_scores, iou_threshold=0.5)   # Filter images by passing them through NMS

      img_boxes += [*cls_boxes[nms_keep_idx]]           # Agregate cls_boxes into tensors for all classes
      box_stack = torch.stack(img_boxes,0)              # Transform individual tensors into a single box tensor
      img_scores += [*cls_scores[nms_keep_idx]]         # Agregate cls_scores into tensors for all classes
      score_stack = torch.stack(img_scores, 0)          # Transform individual tensors into a single score tensor

      img_cls_pred += [*tensor([c]*len(nms_keep_idx))]
      cls_pred_stack = torch.stack(img_cls_pred, 0)

      batch_mask = score_stack > threshold              # filter final lists tto be greater than threshold
      box_stack = box_stack[batch_mask]                 #   "

      score_stack = score_stack[batch_mask]             #   "
      cls_pred_stack = cls_pred_stack[batch_mask]       #   "
    if 'box_stack' not in locals(): continue            # Failed to find any valid classes
    one_batch_boxes.append(box_stack)                   # Agregate bounding boxes for the batch
    one_batch_scores.append(score_stack)                # Agregate scores for the batch
    one_batch_cls_pred.append(cls_pred_stack)

  # Pad individual box and score tensors into uniform-sized box and score tensors of shapes: (batch, no 0f items in batch, 4) and  (batch, no 0f items in batch, 21)
  one_batch_boxes, one_batch_scores, one_batch_cats = pad_output(one_batch_boxes, one_batch_scores, one_batch_cls_pred, no_classes)

  return (one_batch_boxes, one_batch_cats)