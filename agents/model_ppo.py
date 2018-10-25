import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
from agents.utils import soft_update

def layer_init(layer, w_scale=1.0):
    nn.init.orthogonal_(layer.weight.data)
    layer.weight.data.mul_(w_scale)
    nn.init.constant_(layer.bias.data, 0)
    return layer

class Gaussian(nn.Module):
    def __init__(self, state_size, action_size):
        super().__init__()
        # This need a change in I:\MyDev\Anaconda3\envs\drlnd\Lib\site-packages\torch\distributions\utils.py
        # at the line 70, check the type using isinstance instead of __class__.__name__
        self.std = torch.nn.Parameter(torch.ones(1, action_size))
        self.actor = FullyConnected([state_size, 128, 128, action_size], activation=F.relu)
        self.critic = FullyConnected([state_size, 128, 128, 1], activation=F.relu)
    
    def forward(self, state, action=None):
        """
            The actor network gets the parameters of the state inputs
            Then generate a settings mu of a gaussian distribution for each type of action with std as standard deviation
            Afterwards, that distribution is sampled, and we get values for the actions
            That allows us to get also the log probability of the sampled values
            
            When an action is provided, the actor network generates the mu from the state inputs
            We can look then for the log probability of the provided action in regards to the distribution generated by the network
        """
        mu = F.tanh(self.actor(state))
        dist = torch.distributions.Normal(mu, self.std)
        if action is None:
            action = dist.sample()
        log_prob = dist.log_prob(action)
        log_prob = log_prob.sum(dim=-1, keepdim=True)
        value = self.critic(state).squeeze()
        return action, log_prob, value

class FullyConnected(nn.Module):
    def __init__(self, hidden_layers_size, activation=F.relu):
        """Initialize parameters and build model.
        Params
        ======
            state_size (int): Dimension of each state
            action_size (int): Dimension of action space
        """
        super().__init__()
        self.hidden_layers = nn.ModuleList()
        self.hidden_layers.extend([layer_init(nn.Linear(hidden_layers_size[i], hidden_layers_size[i + 1])) for i in range(len(hidden_layers_size) - 1)])
        layer_init(self.hidden_layers[-1], 1e-3)
        self.activation = activation
        
    def forward(self, x):
        """Build a network that maps state to actions."""
        for i in range(len(self.hidden_layers) - 1):
            linear = self.hidden_layers[i]
            x = self.activation(linear(x))
        return self.hidden_layers[-1](x)
