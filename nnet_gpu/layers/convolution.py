#!/usr/bin/env python3
from .Layer import *

im2col = cp.ElementwiseKernel(
	'raw T inp, int32 row, int32 col, int32 out_row, int32 out_col,'
	'int32 kh, int32 kw, int32 sy, int32 sx, int32 ph, int32 pw,'
	'int32 dy, int32 dx',
	'T coled',
	'''
		int c0 = i / (kh * kw * out_row * out_col);		// select channel
		int ky = i / (kw * out_row * out_col) % kh;		// select kernel y
		int kx = i / (out_row * out_col) % kw;			// select kernel x
		int out_y = i / out_col % out_row;				// select output y
		int out_x = i % out_col;						// select output x
		int in_y = ky * dy + out_y * sy - ph;
		int in_x = kx * dx + out_x * sx - pw;
		if (in_y >= 0 && in_y < row && in_x >= 0 && in_x < col) {	// if in image bounds
			coled = inp[col * (in_y + row * c0) + in_x];	// choose pixel
		} else {
			coled = 0;						// pad with 0
		}
	''',
	'im2col')

col2im = cp.ElementwiseKernel(
	'raw T coled, int32 row, int32 col, int32 out_row, int32 out_col,'
	'int32 kh, int32 kw, int32 sy, int32 sx, int32 ph, int32 pw,'
	'int32 dy, int32 dx',
	'T inp',
	'''
		int c0 = i / (row * col);
		int y  = i / col % row;
		int x  = i % col;
		T val = 0;
		for (int ky = 0; ky < kh; ++ky) {
			int out_y = (y + ph - ky * dy);
			if (0 > out_y || out_y >= out_row * sy) continue;
			if (out_y % sy != 0) continue;
			out_y /= sy;
			for (int kx = 0; kx < kw; ++kx) {
				int out_x = (x + pw - kx * dx);
				if (0 > out_x || out_x >= out_col * sx) continue;
				if (out_x % sx != 0) continue;
				out_x /= sx;
				int k = out_y + out_row * (kx + kw * (ky + kh * c0));
				val = val + coled[out_x + out_col * k];
			}
		}
		inp = val;
	''',
	'col2im')

def init_kernel_bias(num_inp_channels, kernel_size, num_kernels,mean=0,std=0.01,dtype=cp.float32):
		weights = std*cp.random.randn(num_inp_channels, kernel_size[0], kernel_size[1], num_kernels) + mean
		# weights/=cp.sqrt(num_inp_channels)
		bias = std*cp.random.randn(1,num_kernels) + mean
		return weights.astype(dtype,copy=False), bias.astype(dtype,copy=False)

class _emptyHelper:
	def __init__(shape):
		self.shape=shape

class conv2d(Layer):
	def __init__(self,num_kernels=0,input_shape=None,kernel_size=0,kernels=None,activation=echo,biases=0,stride=(1,1),dilation=(1,1),padding=None,batches=1,backp=True,std=0.01,name=None,out_row=None,out_col=None,off_transpose=0):		#padding=(ksz-1)/2 for same shape in stride 1
		#input_shape[row,col,channels], kernels(channels,ksz[0],ksz[1],num_kernels), biases[1,num_ker], stride[row,col]
		super().__init__()
		if input_shape is None:
			input_shape=seq_instance.get_inp_shape()
		if name is None:
			self.name=self.__class__.__name__
		else:
			self.name=name
		self.activation=activation
		self.dtype=cp.float32
		self.stride=stride
		self.type=self.__class__.__name__
		self.input_shape=input_shape
		self.row,self.col,self.channels=input_shape
		self.batches=batches
		self.kernels=kernels
		if self.kernels is None:
			if np.isscalar(kernel_size):
				self.kernel_size=(kernel_size,kernel_size)
			else:
				self.kernel_size=kernel_size
			self.num_kernels=num_kernels
			self.kernels,self.biases = init_kernel_bias(self.channels,self.kernel_size,self.num_kernels,std=std,dtype=self.dtype)
		else:
			self.kernel_size=kernels.shape[1:3]
			self.num_kernels=kernels.shape[3]
		self.w_m=cp.zeros_like(self.weights)
		self.w_v=cp.zeros_like(self.weights)
		self.bias_is_not_0=True
		if cp.isscalar(self.biases):				# DO BETTER FIX
			if self.biases==0:
				self.bias_is_not_0=False
		if self.bias_is_not_0:
			self.b_m=cp.zeros_like(self.biases)
			self.b_v=cp.zeros_like(self.biases)
		self.weights = self.kernels
		self.dilation= dilation
		self.padding = padding
		if padding == None:
			self.padding=((self.kernel_size[0]-1)//2,(self.kernel_size[1]-1)//2)		#currently don't give 'even' kernel_size
		if out_row is None:
			self.out_row=self.cal_outsize(self.row,self.kernel_size[0],self.stride[0],self.padding[0],self.dilation[0])
		else:
			self.out_row=out_row
		if out_col is None:
			self.out_col=self.cal_outsize(self.row,self.kernel_size[1],self.stride[1],self.padding[1],self.dilation[1])
		else:
			self.out_col=out_col
		self.param=(self.kernel_size[0]*self.kernel_size[1]*self.channels+1)*self.num_kernels
		self.shape=(None,self.out_row,self.out_col,self.num_kernels)
		self.is_not_dker=True
		if backp:
			self.init_back()

	def init_back(self):
		grads = _emptyHelper((self.batches,self.out_row,self.out_col,self.num_kernels))
		self.d_ker=conv2d(input_shape=(self.row,self.col,self.batches),kernels=grads,activation=echo,dilation=self.stride,padding=self.padding,backp=False,out_row=self.kernel_size[0],out_col=self.kernel_size[1])
		self.d_ker.is_not_dker=False
		self.d_inp=conv2dtranspose(input_shape=(self.out_row,self.out_col,self.num_kernels),kernels=self.kernels,activation=echo,stride=self.stride,padding=self.padding,dilation=self.dilation,backp=False,out_row=self.row,out_col=self.col)

	def cal_outsize(self,sz,ksz,stride,pad,dilation=1):
		dksz = (ksz-1)*dilation + 1		# dilated kernel
		return (sz + 2*pad - dksz)//stride + 1

	def forward(self,inp,training=True):
		self.inp=cp.ascontiguousarray(inp.transpose(0,3,1,2))
		#inp[batches,channels,row,col]
		self.batches,self.channels,self.row,self.col=self.inp.shape
		col = cp.empty((self.batches, self.channels, self.kernel_size[0], self.kernel_size[1], self.out_row, self.out_col), dtype=self.dtype)
		im2col(inp.reduced_view(), self.row, self.col, self.out_row, self.out_col,
				self.kernel_size[0], self.kernel_size[1], self.stride[0], self.stride[1], self.padding[0], self.padding[1],
				self.dilation[0], self.dilation[1],
				col)
		self.z_out = cp.tensordot(col, self.kernels, ((1, 2, 3), (0, 1, 2)))
		# del col
		if self.bias_is_not_0:
			self.z_out+=self.biases
		assert self.z_out.shape==(self.batches,self.out_row,self.out_col,self.num_kernels)
		self.a_out=self.activation(self.z_out)
		return self.a_out				# a_out[self.batches,self.out_row,self.out_col,self.num_kernels]

	def backprop(self,grads,layer=1):								#strides[batch,row,col,depth]
		#grads[batches,esz,esz,num_kernels],inp[batches,channels,row,col],kernels(channels,kernel_size[0],kernel_size[1],num_kernels),biases[1,num_kernels],stride[row,col]
		if self.activation != echo:
			grads*=self.activation(self.z_out,self.a_out,derivative=True)
		self.d_ker.kernels=grads
		self.d_c_w=self.d_ker.forward(self.inp.transpose(1,2,3,0))	#[channels,row,col,batches]
		# self.d_c_w/=self.batches		#take mean change over batches
		# Backprop for inp.	grads[batches,esz,esz,num_kernels]	self.flipped[num_kernels,kernel_size[0],kernel_size[1],channels]
		if layer:
			d_inputs=self.d_inp.forward(grads)
		else:
			d_inputs=0
		if self.bias_is_not_0:
			self.d_c_b=self.grads.reshape(-1,self.num_kernels).sum(axis=0,keepdims=True)
			# self.d_c_b=self.grads.reshape(-1,self.num_kernels).mean(axis=0,keepdims=True)
		return d_inputs

class conv2dtranspose(conv2d):
	def __init__(self,num_kernels=0,input_shape=None,kernel_size=0,kernels=None,activation=echo,biases=0,stride=(1,1),dilation=(1,1),padding=None,batches=1,backp=True,std=0.01,name=None,out_row=None,out_col=None):
		super().__init__(num_kernels=num_kernels,input_shape=input_shape,kernel_size=kernel_size,kernels=kernels,activation=activation,biases=biases,stride=stride,dilation=dilation,padding=padding,batches=batches,backp=backp,std=std,name=name,out_row=out_row,out_col=out_col)

	def cal_outsize(self,sz,ksz,stride,pad,dilation=1):
		# dksz = (ksz-1)*dilation + 1		# dilated kernel
		return sz*stride

	def forward(self,inp,training=True):
		self.inp=inp.transpose(0,3,1,2)
		#inp[batches,channels,row,col]
		col=cp.tensordot(self.kernels,self.inp,(3,1))
		col=cp.rollaxis(col, 3)
		col=cp.ascontiguousarray(col)
		self.z_out=cp.empty((self.batches, self.channels, self.out_row, self.out_col), dtype=gcol.dtype)
		col2im(col.reduced_view(), self.out_row, self.out_col, self.row, self.col,
				self.kernel_size[0], self.kernel_size[1], self.stride[0], self.stride[1], self.padding[0], self.padding[1],
				self.dilation[0], self.dilation[1],
				self.z_out)
		self.a_out=self.activation(self.z_out)
		return self.a_out.transpose(0,2,3,1)			# a_out[self.batches,self.out_row,self.out_col,self.num_kernels]

	def backprop(self,grads,layer=1):
		pass