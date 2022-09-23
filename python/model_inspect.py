# %%
# imports
import platform

import numpy as np
import pandas as pd
import torch
import torchvision
from emonet_utils import EmoNet
from image_utils import NSDDataset
from torch import nn
from torchvision import transforms
from tqdm import tqdm, trange

# %%
# Set abs paths based on which cluster node we're on
base_path = '/data/eccolab/'
if platform.node() != 'ecco':
    base_path = '/home'+base_path

emonet_path = '../ignore/models/EmoNet.pt'
nsd_path = base_path+'Code/NSD/'

# %%
# Define hook functions to get intermediate activations
# Many thanks to https://web.stanford.edu/~nanbhas/blog/forward-hooks-pytorch/

activations = {}
def cache_layer_activation(name):
    def hook(model, input, output):
        # TODO: Figure out how to get this to return the detached output
        # instead of doing this as a side effect
        activations[name] = output.detach().numpy()
    return hook

# %%
# Load that puppy in
emonet_torch = EmoNet()
emonet_torch.load_state_dict(state_dict=torch.load(emonet_path))

# Decorate a call with @torch.no_grad() to Turn OFF gradient tracking because we don't need to train new weights
# parameters() is an Iterator object,
# which means you can do shit to each element in a for loop
# but you can't necessarily index into each element of it
for param in emonet_torch.parameters():
    param.requires_grad = False

# Register the dang hooks to pull intermediate activations
for name, mod in emonet_torch.named_modules():
    if name.startswith('Conv'):
        mod.register_forward_hook(cache_layer_activation(name))

# %%
# Preload ze NSD image data
# Use the NSD images, not the original COCO images/API, even though they're in torchvision
# because the NSD images come pre-cropped and with their own metadata
# It doesn't take that long because HDF5 lazy-load! Yay, I think
# Gotta resize to 227x227 because that's how AlexNet from Matlab likes things
# But do NOT rescale RGB to 0-1 because AlexNet from Matlab likes 0-255
# TODO: Figure out if we need to use any of the image caching I saw in that guy's GitHub Gist
nsd_transform = transforms.Compose([
                        transforms.Resize((227, 227)),
                        transforms.PILToTensor()
                        ])

nsd_torchdata = NSDDataset(root=nsd_path+'stimuli/',
                           annFile=nsd_path+'nsd_stim_info_merged.csv',
                           shared1000=True,
                           transform=nsd_transform)

# %%
# Initialize ze DataLoader to actually feed into the model

#
batch_size = 10
nsd_torchloader = torch.utils.data.DataLoader(nsd_torchdata, batch_size=batch_size)
# %%
# DO IT?! RUN IT! GET PREDS
emonet_torch.eval()

# Yeah I think we should set this to empty dict again just in case
# It needs to be initalized earlier for that function to work I think
# but for safety, re-set it to empty before every pass of the model
# TODO: Write this to preallocate so we can copy into Tensor slice and go more pythonically
activations_all = {
    'Conv_0': [],
    'Conv_1': [],
    'Conv_2': [],
    'Conv_3': [],
    'Conv_4': [],
    'Conv_5': [],
    'Conv_6': [],
    'Conv_7': [],
    }
activations = {}
preds_all = []
pred = []

for img, lab in tqdm(nsd_torchloader):
    pred = emonet_torch(img)
    preds_all.append(pred.numpy())
    for layer in activations_all.keys():
        activations_all[layer].append(activations[layer])

    # Clear out activations before next img
    activations = {}


# %%
# Get output arrays into 2D form with one row per stimulus
preds_all = np.concatenate(preds_all, axis=0)

for layer in activations_all.keys():
    # reshape each batch to 2d
    activations_all[layer] = [act.reshape(batch_size, -1) for act in activations_all[layer]]
    # once each is internally 2d, unnest longer by concatenating
    activations_all[layer] = np.concatenate(activations_all[layer], axis=0)

# %%
# Generate correlation matrices

cormats = {
    'Conv_0': [],
    'Conv_1': [],
    'Conv_2': [],
    'Conv_3': [],
    'Conv_4': [],
    'Conv_5': [],
    'Conv_6': [],
    'Conv_7': [],
    }

# corrcoef does actually expect observations to go by rows as default
for layer in cormats.keys():
    cormats[layer] = np.corrcoef(activations_all[layer])

# %%
# Write correlation matrices out teehee

for layer in tqdm(cormats.keys()):
    np.savetxt('../ignore/outputs/emonet_torch_cormat_layer_{}.txt'.format(layer),
               cormats[layer],
               fmt='%.9f',
               delimiter=',')

# %%
# euclidean distances, actually

distances = {
    'Conv_0': [],
    'Conv_1': [],
    'Conv_2': [],
    'Conv_3': [],
    'Conv_4': [],
    'Conv_5': [],
    'Conv_6': [],
    'Conv_7': [],
    }

for layer in distances.keys():
    print('Starting layer {}...'.format(layer))
    distances[layer] = np.zeros((activations_all[layer].shape[0], activations_all[layer].shape[0]))
    for row in trange(activations_all[layer].shape[0]):
        for col in range(row):
            distance = np.linalg.norm(activations_all[layer][col, :] - activations_all[layer][row, :])
            distances[layer][row, col] = distance

# %%
# Write distance matrices out

for layer in tqdm(distances.keys()):
    np.savetxt('../ignore/outputs/emonet_torch_distmat_layer_{}.txt'.format(layer),
               distances[layer],
               fmt='%.9f',
               delimiter=',')
# %%
