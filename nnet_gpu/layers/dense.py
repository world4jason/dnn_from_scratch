#!/usr/bin/env python3
from .base_layer import *
from . import seqinst

class dense(Layer):
	def __init__(self,num_out,input_shape=None,weights=None,biases=None,activation=echo,mean=0,std=0.01,name=None):
		super().__init__()
		self.dtype=np.float32
		self.type=self.__class__.__name__
		if name is None:
			self.name=self.__class__.__name__
		else:
			self.name=name
		if input_shape is None:
			self.input_shape=seqinst.seq_instance.get_inp_shape()[0]
		else:
			self.input_shape=input_shape
		self.activation=activation
		if weights is None:
			self.weights = std*cp.random.randn(self.input_shape,num_out).astype(self.dtype,copy=False) + mean
			# weights/=np.sqrt(self.input_shape)
		else:
			if weights.shape!=(self.input_shape,num_out):
				raise Exception("weights should be of shape: "+str((self.input_shape,num_out)))
			else:
				self.weights = cp.asarray(weights)
		if biases is None:
			self.biases = std*cp.random.randn(1,num_out).astype(self.dtype,copy=False) + mean
		else:
			if biases.shape!=(1,num_out):
				raise Exception("biases should be of shape: "+str((1,num_out)))
			else:
				self.biases = cp.asarray(biases)
		self.kernels = self.weights
		self.w_m=cp.zeros_like(self.weights)
		self.w_v=cp.zeros_like(self.weights)
		self.b_m=cp.zeros_like(self.biases)
		self.b_v=cp.zeros_like(self.biases)
		self.shape=(None,num_out)
		self.param=self.input_shape*num_out + num_out
		self.not_softmax_cross_entrp=True
		if self.activation==echo:
			self.notEcho=False
		else:
			self.notEcho=True

	def forward(self,inp,training=True):
		self.inp=cp.asarray(inp)
		self.z_out=self.inp.dot(self.weights)+self.biases
		self.a_out=self.activation(self.z_out)
		return self.a_out

	def backprop(self,grads,layer=1):
		if self.notEcho and self.not_softmax_cross_entrp:			# make it better in future
			grads*=self.activation(self.z_out,self.a_out,derivative=True)
		self.d_c_w=self.inp.T.dot(grads)#/self.inp.shape[0]
		if layer:
			d_c_a=grads.dot(self.weights.T)
		else:
			d_c_a=0
		self.d_c_b=grads.sum(axis=0,keepdims=True)
		# self.d_c_b=grads.mean(axis=0,keepdims=True)
		return d_c_a