
import os
import sys

import torch
import torchvision
from torchvision.transforms import v2
from torch import nn
from torchsummary import summary

import pandas as pd
import numpy as np
import matplotlib
from matplotlib import pyplot as plt
import seaborn as sns

from PIL import Image
import tqdm.notebook as tqdm

# sys.path.append('../dataset_construction')
# from model_training_utils import *


img_type = 'raw-derivative.-60'

# ---- Plotting ----
plt.figure(figsize=(15, 10))

def plot_loss(log, save=True):
    train_loss = log['train']['loss']
    val_loss = log['val']['loss']

    plt.plot(train_loss, label="training loss")
    plt.plot(val_loss, label="validation loss")

    plt.legend()
    plt.xlabel("epoch")
    plt.ylabel("loss")

    plt.title("Cloud-Detection Training and Validation Loss vs Epoch")
    if save:
        plt.savefig("Loss")
        plt.close()

def plot_accuracy(log, save=True):
    train_acc = log['train']['acc']
    val_acc = log['val']['acc']

    plt.plot(train_acc, label="training accuracy")
    plt.plot(val_acc, label="validation accuracy")
    plt.legend()
    plt.xlabel("epoch")
    plt.ylabel("accuracy")

    plt.title("Cloud-Detection Training and Validation Accuracy vs Epoch")
    if save:
        plt.savefig(f"Accuracy")
        plt.close()


def plot_cloudy_mistakes(log, save=True):
    train_acc = log['train']['cloudy_wrong']
    val_acc = log['val']['cloudy_wrong']

    plt.plot(train_acc, label="training cloudy_wrong")
    plt.plot(val_acc, label="validation cloudy_wrong")
    plt.legend()
    plt.xlabel("epoch")
    plt.ylabel("accuracy")

    plt.title("Cloud-Detection Training and percent cloudy misclassifications vs Epoch")
    if save:
        plt.savefig(f"cloudy_wrong")
        plt.close()


def plot_clear_mistakes(log, save=True):
    train_acc = log['train']['clear_wrong']
    val_acc = log['val']['clear_wrong']

    plt.plot(train_acc, label="training clear_wrong")
    plt.plot(val_acc, label="validation clear_wrong")
    plt.legend()
    plt.xlabel("epoch")
    plt.ylabel("accuracy")

    plt.title("Cloud-Detection Training and percent clear misclassifications vs Epoch")
    if save:
        plt.savefig(f"clear_wrong")
        plt.close()


# Utils

def get_device(verbose=False):
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available() and torch.backends.mps.is_built():
        device = "mps"
    else:
        device = "cpu"
    if verbose: print(f"Using device {device}")
    return device


def weights_init(m):
    if isinstance(m, nn.Conv2d):
        nn.init.xavier_uniform_(m.weight.data, gain=nn.init.calculate_gain('relu'))
    if isinstance(m, nn.LazyLinear):
        nn.init.xavier_uniform_(m, gain=nn.init.calculate_gain('relu'))
    elif isinstance(m, nn.Linear):
        nn.init.xavier_uniform_(m, gain=nn.init.calculate_gain('relu'))
    elif isinstance(m, nn.BatchNorm1d):
        nn.init.xavier_uniform_(m, gain=nn.init.calculate_gain('relu'))
    elif isinstance(m, nn.BatchNorm2d):
        nn.init.xavier_uniform_(m.weight.data, gain=nn.init.calculate_gain('relu'))


class Trainer:

    def __init__(self, model, optimizer, loss_fn, train_loader, val_loader, epochs=1, gamma=0.9, do_summary=True):
        self.model = model
        self.optimizer = optimizer
        self.loss_fn = loss_fn
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.epochs = epochs
        self.gamma = gamma
        self.cloudy_wrong_data = []
        self.clear_wrong_data = []
        self.device = get_device()
        self.training_log = self.make_training_log()
        if do_summary:
            self.get_model_summary()

    def make_training_log(self):
        training_log = {
            'train': {
                'loss': [],
                'acc': [],
                'cloudy_wrong': [],
                'clear_wrong': []
            },
            'val': {
                'loss': [],
                'acc': [],
                'cloudy_wrong': [],
                'clear_wrong': []
            }
        }
        return training_log

    def get_model_summary(self):
        """Get the current model configuration."""
        self.model.to(device=self.device)
        self.model.eval()
        with torch.no_grad():
            img_data, y = next(iter(self.train_loader))
            x = img_data[img_type]
            x = x.to(device=self.device, dtype=torch.float)
            self.model(x)
        s = None
        try:
            s = summary(self.model)
            with open('../model_training/model_summary.txt', 'w') as f:
                f.write(str(s))
        except ValueError as verr:
            print(verr)
        return s

    def record_acc_and_loss(self, dataset_type):
        """
        @param dataset_type: 'train' or 'val
        """
        ncorrect = 0
        nsamples = 0
        loss_total = 0
        ncloudy_wrong = 0
        nclear_wrong = 0
        data_loader = self.train_loader if dataset_type == 'train' else self.val_loader

        self.model.eval()
        with torch.no_grad():
            for img_data, y in data_loader:
                x = img_data[img_type]
                x = x.to(device=self.device, dtype=torch.float)
                y = y.to(device=self.device, dtype=torch.long)
                scores = self.model(x)

                loss = self.loss_fn(scores, y)
                loss_total += loss.item()

                predictions = torch.argmax(scores, dim=1)
                ncorrect += (predictions == y).sum()

                # if ((predictions == 1) & (predictions != y)).cpu().any():
                #     for im, pred in zip(x, predictions):
                #         cloudy_wrong_data.append(im.cpu())
                # elif ((predictions == 0) & (predictions != y)).cpu().any():
                #     for i in range(len(predictions)):
                #         if predictions[i] == 0 and predictions[i] != y[i]:
                #             clear_wrong_data.append(x[i].cpu())
                for i in range(len(predictions)):
                    if predictions[i] == 1 and predictions[i] != y[i]:
                        self.cloudy_wrong_data.append(x[i].cpu())
                    elif predictions[i] == 0 and predictions[i] != y[i]:
                        self.clear_wrong_data.append(x[i].cpu())

                ncloudy_wrong += ((predictions == 1) & (predictions != y)).cpu().sum()
                nclear_wrong += ((predictions == 0) & (predictions != y)).cpu().sum()
                nsamples += predictions.size(0)

            avg_loss = loss_total / len(data_loader)
            acc = float(ncorrect) / nsamples

            self.training_log[dataset_type]['loss'].append(avg_loss)
            self.training_log[dataset_type]['acc'].append(acc)
            self.training_log[dataset_type]['cloudy_wrong'].append(ncloudy_wrong / max(nsamples - float(ncorrect), 1))
            self.training_log[dataset_type]['clear_wrong'].append(nclear_wrong / max(nsamples - float(ncorrect), 1))

            report = "{0}: \tloss = {1:.4f},  acc = {2}/{3} ({4:.2f}%)".format(
                dataset_type.capitalize().rjust(10), avg_loss, ncorrect, nsamples, acc * 100)
            return report

    def train(self):
        """
        Train the given model and report accuracy and loss during training.

        Inputs:
        - model: A PyTorch Module giving the model to train.
        - optimizer: An Optimizer object we will use to train the model
        - epochs: (Optional) A Python integer giving the number of epochs to train for

        Returns: dictionary of train and validation loss and accuracy for each epoch.
        """
        # Move model to device
        model = self.model.to(device=self.device)

        # Init LR schedulers
        scheduler_exp = torch.optim.lr_scheduler.ExponentialLR(self.optimizer, gamma=self.gamma)
        scheduler_plat = torch.optim.lr_scheduler.ReduceLROnPlateau(self.optimizer)

        for e in range(1, self.epochs + 1):
            print(f"\n\nEpoch {e}")
            for img_data, y in tqdm.tqdm(self.train_loader, unit="batches"):
                model.train()
                x = img_data[img_type]
                x = x.to(device=self.device, dtype=torch.float)
                y = y.to(device=self.device, dtype=torch.long)

                # Forward pass: compute class scores
                scores = model(x)
                loss = self.loss_fn(scores, y)

                # Remove the gradients from the previous step
                self.optimizer.zero_grad()

                # Backward pass: update weights
                loss.backward()
                self.optimizer.step()

            # Update log of train and validation accuracy and loss. Print progress.
            train_report = self.record_acc_and_loss('train')
            valid_report = self.record_acc_and_loss('val')
            print(valid_report, '\n', train_report)

            # Save model parameters with the best validation accuracy
            val_accs = self.training_log['val']['acc']
            if val_accs[-1] == max(val_accs):
                torch.save(model.state_dict(), "../model_training/best_cloud_detection_model.pth")

            # Update optimizer
            scheduler_exp.step()
            scheduler_plat.step(self.training_log['val']['loss'][-1])
        print('Done training')
        plot_accuracy(self.training_log)
        plot_loss(self.training_log)
        plot_cloudy_mistakes(self.training_log)
        plot_clear_mistakes(self.training_log)
        plt.close()