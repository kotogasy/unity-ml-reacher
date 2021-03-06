import numpy as np

import torch
import torch.nn.functional as F
import torch.optim as optim
from collections import deque
import random
from agents.utils import soft_update


class DDPG():
    """Interacts with and learns from the environment."""

    def __init__(self, state_size, action_size, seed, memory, ActorNetwork, CriticNetwork, device,
                BOOTSTRAP_SIZE = 5,
                GAMMA = 0.99, 
                TAU = 1e-3, 
                LR_CRITIC = 5e-4,
                LR_ACTOR = 5e-4, 
                UPDATE_EVERY = 1,
                TRANSFER_EVERY = 2,
                UPDATE_LOOP = 10,
                ADD_NOISE_EVERY = 5,
                WEIGHT_DECAY = 0,
                FILE_NAME="ddpg"):
        """Initialize an Agent object.
        
        Params
        ======
            state_size (int): dimension of each state
            action_size (int): dimension of each action
            seed (int): random seed
            num_agents: number of running agents
            memory: instance of ReplayBuffer
            ActorNetwork: a class inheriting from torch.nn.Module that define the structure of the actor neural network
            CriticNetwork: a class inheriting from torch.nn.Module that define the structure of the critic neural network
            device: cpu or cuda:0 if available
            BOOTSTRAP_SIZE: length of the bootstrap
            GAMMA: discount factor
            TAU: for soft update of target parameters
            LR_CRITIC: learning rate of the critics
            LR_ACTOR: learning rate of the actors
            UPDATE_EVERY: how often to update the networks
            TRANSFER_EVERY: after how many update do we transfer from the online network to the targeted fixed network
            ADD_NOISE_EVERY: how often to add noise to favor exploration
            FILE_NAME: default prefix to the saved model
        """
        self.seed = random.seed(seed)
        
        # Actor networks
        self.actor_local = ActorNetwork(state_size, action_size, seed).to(device)
        self.actor_optim = optim.Adam(self.actor_local.parameters(), lr=LR_ACTOR)
        self.actor_target = ActorNetwork(state_size, action_size, seed).to(device)
                 
        # Critic networks
        self.critic_local = CriticNetwork(state_size, action_size, seed).to(device)
        self.critic_optim = optim.Adam(self.critic_local.parameters(), lr=LR_CRITIC, weight_decay=WEIGHT_DECAY)
        self.critic_target = CriticNetwork(state_size, action_size, seed).to(device)
        
        # Ensure that at the begining, both target and local are having the same parameters
        soft_update(self.actor_local, self.actor_target, 1)
        soft_update(self.critic_local, self.critic_target, 1)
        
        self.device = device
        
        # Noise
        self.noise = None
        
        # Replay memory
        self.memory = memory
        # Initialize time steps (for updating every UPDATE_EVERY steps)
        self.u_step = 0
        self.n_step = 0
        
        self.BOOTSTRAP_SIZE = BOOTSTRAP_SIZE
        self.GAMMA = GAMMA
        self.TAU = TAU
        self.LR_CRITIC = LR_CRITIC
        self.LR_ACTOR = LR_ACTOR
        self.UPDATE_EVERY = UPDATE_EVERY
        self.TRANSFER_EVERY = TRANSFER_EVERY
        self.UPDATE_LOOP = UPDATE_LOOP
        self.ADD_NOISE_EVERY = ADD_NOISE_EVERY
        self.FILE_NAME = FILE_NAME
        
        # for bootstrap purpose
        self.rewards = deque(maxlen=BOOTSTRAP_SIZE)
        self.states = deque(maxlen=BOOTSTRAP_SIZE)
        self.actions = deque(maxlen=BOOTSTRAP_SIZE)
        self.gammas = np.array([GAMMA ** i for i in range(BOOTSTRAP_SIZE)])
    
    def reset(self):
        if self.noise:
            self.noise.reset()
        
    def set_noise(self, noise):
        self.noise = noise
    
    def save(self):
        torch.save(self.critic_local.state_dict(),"{}_critic.pth".format(self.FILE_NAME))
        torch.save(self.actor_local.state_dict(),"{}_actor.pth".format(self.FILE_NAME))
        torch.save(self.critic_target.state_dict(),"{}_critic_target.pth".format(self.FILE_NAME))
        torch.save(self.actor_target.state_dict(),"{}_actor_target.pth".format(self.FILE_NAME))
     
    def load(self, folder):
        path = "./{}/{}_critic.pth".format(folder,self.FILE_NAME)
        self.critic_local.load_state_dict(torch.load(path))
        path = "./{}/{}_actor.pth".format(folder,self.FILE_NAME)
        self.actor_local.load_state_dict(torch.load(path))
        path = "./{}/{}_critic_target.pth".format(folder,self.FILE_NAME)
        self.critic_target.load_state_dict(torch.load(path))
        path = "./{}/{}_actor_target.pth".format(folder,self.FILE_NAME)
        self.actor_target.load_state_dict(torch.load(path))
    
    def act(self, state, add_noise=True):
        """Returns actions of each actor for given states.
        
        Params
        ======
            state (array_like): current states
        """
        ret = None
        
        self.n_step = (self.n_step + 1) % self.ADD_NOISE_EVERY
        
        with torch.no_grad():
            if add_noise and self.noise and self.n_step == 0:
                self.actor_local.eval()
                state = torch.from_numpy(state).float().unsqueeze(0).to(self.device)
                to_add = self.noise.apply(self.actor_local, state)
                if ret is None:
                    ret = to_add
                else:
                    ret = np.concatenate((ret, to_add))
                self.actor_local.train()
            else:
                self.actor_local.eval()
                state = torch.from_numpy(state).float().unsqueeze(0).to(self.device)
                to_add = self.actor_local(state).cpu().data.numpy()
                if ret is None:
                    ret = to_add
                else:
                    ret = np.concatenate((ret, to_add))
                self.actor_local.train()
        return ret
    
    def step(self, state, action, reward, next_state, done):
        # Save experience in replay memory
        
        self.rewards.append(reward)
        self.states.append(state)
        self.actions.append(action)
        if len(self.rewards)==self.BOOTSTRAP_SIZE:
            reward = np.sum(self.rewards * self.gammas)
            self.memory.add(self.states[0], self.actions[0], reward, next_state, done)
                                                
        # Learn every UPDATE_EVERY time steps.
        self.u_step = (self.u_step + 1) % self.UPDATE_EVERY     
        if len(self.memory) > self.memory.batch_size and self.u_step == 0:   
            t_step=0
            for _ in range(self.UPDATE_LOOP):
                self.learn()
                t_step=(t_step + 1) % self.TRANSFER_EVERY
                if t_step == 0:
                    soft_update(self.actor_local, self.actor_target, self.TAU)
                    soft_update(self.critic_local, self.critic_target, self.TAU)
    
    def learn(self):
        """Update value parameters using given batch of experience tuples.

        Params
        ======
            experiences (Tuple[torch.Variable]): tuple of (s, a, r, s', done) tuples
        """
        # shuffle all memory to disrupt the internal correlation and learn from all of them
        states, actions, rewards, next_states, dones = self.memory.sample()

        # The critic should estimate the value of the states to be equal to rewards plus
        # the estimation of the next_states value according to the critic_target and actor_target
        with torch.no_grad():
            self.actor_target.eval()
            next_actions = self.actor_local(next_states)
            self.critic_target.eval()
            targeted_value = rewards + (self.GAMMA**self.BOOTSTRAP_SIZE)*self.critic_target(next_states, next_actions)*(1 - dones)
        current_value = self.critic_local(states, actions)

        # calculate the loss
        self.critic_optim.zero_grad()
        loss = F.mse_loss(current_value, targeted_value)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.critic_local.parameters(), 1)
        self.critic_optim.step()

        self.actor_optim.zero_grad()
        actions_pred = self.actor_local(states)
        mean = self.critic_local(states, actions_pred).mean()
        (-mean).backward()
        self.actor_optim.step()    