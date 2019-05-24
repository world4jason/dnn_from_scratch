#!/usr/bin/env python3
import numpy as np

sd=np.random.randint(1000)
# print(sd)
np.random.seed(sd)	#470

class conv_net:
	def __init__(self):
		self.learning_rate=0.01

	def init_kernel_bias(self, num_inp_channels, kernel_size, num_kernels):
		shape = [num_inp_channels, kernel_size, kernel_size, num_kernels]
		weights = 0.1*np.random.randn(*shape)
		bias = 0.5*np.random.randn(1,num_kernels)
		return weights, bias

	def __str__(self):
		return str(self.__dict__)

	def sigmoid(self,x):
		x=np.clip(x,-500,500)
		return 1.0/(1+np.exp(-x))

	def sigmoid_der(self,x,y):
		return x * (1 - x)

	def elliot_function( signal, derivative=False ):
		""" A fast approximation of sigmoid """
		s = 1 # steepness
		
		abs_signal = (1 + np.abs(signal * s))
		if derivative:
			return 0.5 * s / abs_signal**2
		else:
			# Return the activation signal
			return 0.5*(signal * s) / abs_signal + 0.5

	def relu(self,x):
		return x*(x>0)

	def relu_der(self,x,y):
		return (y > 0)*1

	def softmax(self,x):
		# exps = np.exp(x)
		exps = np.exp(x-np.max(x, axis=1, keepdims = True))
		return exps/np.sum(exps, axis=1, keepdims = True)

	def soft_der(self,x,y):
		return np.ones(self.softmax(x).shape)

	def del_cross_soft(self,out,res):
		res = res.argmax(axis=1)
		m = res.shape[0]
		grad = out
		grad[range(m),res]-=1
		grad = grad/m
		return grad

	def normalize(self,x):
		mn=x.min()
		mx=x.max()
		x = (x-mn)/(mx-mn)
		return x

	def batch_norm(self,aa):
		gamma=aa.std()
		beta=aa.mean()
		ad=(aa-beta)/gamma				# normalize
		ad=ad*gamma+beta				# recover
		return ad

	def conv2d(self,inp,kernels,biases,stride=[1,1],padding=0):		#padding=(ksz-1)/2 for same shape in stride 1
		#inp[batches,row,col,d],kernels(d,ksz,ksz,num_ker),biases[1,num_ker],stride[row,col]
		inp=inp.transpose(0,3,1,2)	#inp[batches,d,row,col]
		output=[]
		ksz=kernels.shape[1]
		if not padding:							#take care of padding in backprop too
			padding=(ksz-1)//2					#currently don't give even ksz
		out_row,out_col=((inp.shape[2]-ksz+2*padding)//stride[0]+1),((inp.shape[3]-ksz+2*padding)//stride[1]+1)
		for img in inp:		#img[d,row,col]		#TODO: MAKE THIS FOR LOOP INTO SINGLE NUMPY OPERATION
			padded=np.zeros((img.shape[0],img.shape[1]+2*padding,img.shape[2]+2*padding))
			padded[:,padding:-padding,padding:-padding]=img
			# Take all windows into a matrix
			d,row,col=padded.shape
			window=(np.arange(ksz)[:,None]*row+np.arange(ksz)).ravel()+np.arange(d)[:,None]*row*col
			slider=(np.arange(out_row*stride[0])[:,None]*row+np.arange(out_col*stride[1]))
			# windows(out_row*out_col, ksz*ksz*d) . kernels(d*ksz*ksz,num_ker)
			out=(np.dot(np.take(padded, window.ravel()+slider[::stride[0],::stride[1]].ravel()[:,None]), kernels.reshape(-1,kernels.shape[3])))
			out=(out+biases).reshape(out_row,out_col,kernels.shape[3])
			output.append(out)
		return np.array(output)	#output[batches,out_row,out_col,num_ker]

	def conv2d_back(self,errors,inp,kernels,biases,stride=[1,1],layer=1):								#strides[batch,row,col,depth]
		#errors[batches,esz,esz,num_ker],inp[batches,row,col,d],kernels(d,ksz,ksz,num_ker),biases[1,num_ker],stride[row,col]
		batches,esz,esz,num_ker=errors.shape
		inp=inp.transpose(3,1,2,0)		#inp[d,row,col,batches]
		flipped=np.flip(kernels,(1,2)).transpose(3,1,2,0)	#flipped[num_ker,ksz,ksz,d]
		ksz=flipped.shape[1]
		pad=(ksz-1)//2
		# d_kernels=np.zeros(kernels.shape)
		# for img,error in zip(inp,errors):		#img[d,row,col]
			# Backprop for kernels.				#error[esz,esz,num_ker]
			# d_kernels+=self.conv2d(img.reshape(d,row,col,-1),error.reshape(1,esz,esz,num_ker),0,padding=pad)
			#d_kernels[d,ksz,ksz,num_ker]
		d_kernels=self.conv2d(inp,errors,0,padding=pad)
		d_kernels/=batches		#take mean change over batches
		# Backprop for inp.		errors[batches,esz,esz,num_ker]	flipped[num_ker,ksz,ksz,d]
		if layer:
			d_inputs=self.conv2d(errors,flipped,0)
		else:
			d_inputs=0
		d_bias=errors.reshape(-1,num_ker).mean(axis=0)[None,:]

		return d_inputs, d_kernels*self.learning_rate, d_bias*self.learning_rate

	def max_pool(self,inp,ksize=[2,2],stride=[2,2]):
		#inp[batches,row,col,d], kernels[ksz,ksz], stride[row,col]
		inp=inp.transpose(0,3,1,2)	#inp[batches,d,row,col]
		ksz=ksize[0]
		out_row,out_col=((inp.shape[2]-ksz)//stride[0]+1),((inp.shape[3]-ksz)//stride[1]+1)
		batches,d,row,col=inp.shape
		output=[]
		max_index=[]
		for img in inp:			#img[d,row,col]
			window=(np.arange(ksz)[:,None]*row+np.arange(ksz)).ravel()+np.arange(0,row,stride[0])[:,None]
			window=window.ravel()+np.arange(0,col,stride[1])[:,None]*col
			slider=np.arange(d)[:,None]*row*col
			ind=(window.ravel()+slider.ravel()[:,None]).reshape(-1,ksz*ksz)
			x_col=np.take(img, ind)
			m_ind=x_col.argmax(axis=1)
			out=x_col[range(m_ind.size),m_ind].reshape(-1,out_row,out_col)	#out[d,or,oc]
			max_ind=np.take(ind,np.arange(x_col.shape[0])*x_col.shape[1]+m_ind)
			output.append(out)
			max_index.append(max_ind)
		return np.array(output).transpose(0,2,3,1), np.array(max_index)

	def max_pool_back(self,errors,inp,max_index,ksize=[2,2],stride=[2,2]):
		#errors[batches,esz,esz,d],inp[batches,row,col,d],kernels[ksz,ksz],stride[row,col]
		errors=errors.transpose(0,3,1,2)	#errors[batches,d,esz,esz]
		d_inputs=[]
		batches,row,col,d=inp.shape
		iml=row*col*d
		for error,max_ind in zip(errors,max_index):		#error[d,esz,esz]
			d_img=np.zeros(iml)
			np.add.at(d_img,max_ind,error.ravel())
			d_img=d_img.reshape(d,row,col)		#d_img[d,row,col]
			d_inputs.append(d_img)

		return (np.array(d_inputs).transpose(0,2,3,1))