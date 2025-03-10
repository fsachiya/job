#
# Copyright (c) 2023 Ogata Laboratory, Waseda University
#
# Released under the AGPL license.
# see https://www.gnu.org/licenses/agpl-3.0.txt
#

import os
import sys
import torch
import argparse
import numpy as np
import matplotlib.pylab as plt
import matplotlib.animation as anim
from sklearn.decomposition import PCA

sys.path.append("/Users/sachiya/work/eipl")
from eipl.data import SampleDownloader
from eipl.model import SARNN
from eipl.utils import restore_args, tensor2numpy, normalization


# argument parser
parser = argparse.ArgumentParser()
parser.add_argument("--filename", type=str, default=None)
args = parser.parse_args()

# check args
assert args.filename, "Please set filename"

# restore parameters
dir_name = os.path.split(args.filename)[0]
params = restore_args(os.path.join(dir_name, "args.json"))

# load dataset
minmax = [params["vmin"], params["vmax"]]
grasp_data = SampleDownloader("airec", "grasp_bottle", img_format="HWC")
_images, _joints = grasp_data.load_raw_data("test")
images = _images
joints = _joints
joint_bounds = np.load(
    os.path.join(os.path.expanduser("~"), ".eipl/airec/grasp_bottle/joint_bounds.npy")
)
print("images shape:{}, min={}, max={}".format(images.shape, images.min(), images.max()))
print("joints shape:{}, min={}, max={}".format(joints.shape, joints.min(), joints.max()))

# define model
model = SARNN(
    rec_dim=params["rec_dim"],
    joint_dim=8,
    k_dim=params["k_dim"],
    heatmap_size=params["heatmap_size"],
    temperature=params["temperature"],
)

ckpt = torch.load(args.filename, map_location=torch.device("cpu"))
model.load_state_dict(ckpt["model_state_dict"])
model.eval()

# Inference
states = []
state = None
nloop = images.shape[1]
for loop_ct in range(nloop):
    # load data and normalization
    img_t = images[:, loop_ct].transpose(0, 3, 1, 2)
    img_t = torch.Tensor(img_t)
    img_t = normalization(img_t, (0, 255), minmax)
    joint_t = torch.Tensor(joints[:, loop_ct])
    joint_t = normalization(joint_t, joint_bounds, minmax)

    # predict rnn
    _, _, _, _, state = model(img_t, joint_t, state)
    states.append(state[0])

states = torch.permute(torch.stack(states), (1, 0, 2))
states = tensor2numpy(states)
# Reshape the state from [N,T,D] to [-1,D] for PCA of RNN.
# N is the number of datasets
# T is the sequence length
# D is the dimension of the hidden state
N, T, D = states.shape
states = states.reshape(-1, D)

# plot pca
loop_ct = float(360) / T
pca_dim = 3
pca = PCA(n_components=pca_dim).fit(states)
pca_val = pca.transform(states)
# Reshape the states from [-1, pca_dim] to [N,T,pca_dim] to
# visualize each state as a 3D scatter.
pca_val = pca_val.reshape(N, T, pca_dim)

fig = plt.figure(dpi=60)
ax = fig.add_subplot(projection="3d")


def anim_update(i):
    ax.cla()
    angle = int(loop_ct * i)
    ax.view_init(30, angle)

    c_list = ["C0", "C1", "C2", "C3", "C4"]
    for n, color in enumerate(c_list):
        ax.scatter(pca_val[n, 1:, 0], pca_val[n, 1:, 1], pca_val[n, 1:, 2], color=color, s=3.0)

    ax.scatter(pca_val[n, 0, 0], pca_val[n, 0, 1], pca_val[n, 0, 2], color="k", s=30.0)
    pca_ratio = pca.explained_variance_ratio_ * 100
    ax.set_xlabel("PC1 ({:.1f}%)".format(pca_ratio[0]))
    ax.set_ylabel("PC2 ({:.1f}%)".format(pca_ratio[1]))
    ax.set_zlabel("PC3 ({:.1f}%)".format(pca_ratio[2]))


ani = anim.FuncAnimation(fig, anim_update, interval=int(np.ceil(T / 10)), frames=T)
ani.save("./output/PCA_SARNN_{}.gif".format(params["tag"]))

# If an error occurs in generating the gif animation, change the writer (imagemagick/ffmpeg).
#ani.save("./output/PCA_SARNN_{}.gif".format(params["tag"]), writer="imagemagick")
#ani.save("./output/PCA_SARNN_{}.gif".format(params["tag"]), writer="ffmpeg")
