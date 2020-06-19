import os
import sys
import numpy as np
import pandas as pd
import logging
import gc
import tqdm
import pickle
import json
import time
import tempfile
from gensim.models import Word2Vec
import torch

class train_data_loader(object):
	"""
	Load training label and input
	"""
	def __init__(self, label_artifact_path, seq_inp_target, seq_inp_path, w2v_registry, max_seq_len=100, batch_size=512, shuffle=False, logger=None):
		"""
		: label_artifact_path (str): path to a npy file containing a 1d array
		: seq_inp_target (list[str]): list of embedding variables
		: seq_inp_path (list[str]): list of paths to a pkl file
		: w2v_registry (dict): key is the embedded variable and value is the path to a gensim.models.Word2Vec artifact
		: max_seq_len (int): max length for sequence input, default 100
		: batch_size (int): batch size for yielding data
		: shuffle (bool): whether to shuffle data before yielding

		Sample code
		```python
		label_artifact_path = '/Users/ywu/Desktop/train_toy.npy'
		seq_inp_target = ['product', 'creative']
		seq_inp_path = ['/Users/ywu/Desktop/product_toy.pkl', '/Users/ywu/Desktop/creative_toy.pkl']
		w2v_registry = {
			"product": "/Users/ywu/Desktop/Tencent-Ads-Algo-Comp-2020/Script/embed_artifact/product_embed_s128_j1j5w652",
			"creative": "/Users/ywu/Desktop/Tencent-Ads-Algo-Comp-2020/Script/embed_artifact/creative_embed_s256_5y76t_gp"
		}

		train_loader = train_data_loader(label_artifact_path, seq_inp_target, seq_inp_path, w2v_registry)
		train_iterator = iter(train_loader)
		while True:
			try:
				y, x_seq, x_last_idx = next(train_iterator)
				...
			except:
				break
		del train_iterator, train_loader
		_ = gc.collect()
		```
		"""
		print("#### train data loader: w2v_registry=", w2v_registry)
		print("#### train data loader: seq_inp_target=", seq_inp_target)
		assert label_artifact_path.split('.')[-1]=='npy'
		assert isinstance(seq_inp_target, list), isinstance(seq_inp_path, list) and isinstance(w2v_registry, dict)
		assert all([k in w2v_registry for k in seq_inp_target]) and all([v.split('.')[-1]=='pkl' for v in seq_inp_path])
		self.label_artifact_path = label_artifact_path
		self.seq_inp_target = seq_inp_target
		self.seq_inp_path = seq_inp_path
		self.w2v_registry = w2v_registry
		self.max_seq_len = max_seq_len
		self.batch_size = batch_size
		self.logger = logger
		self.shuffle = shuffle

		if not gc.isenabled(): gc.enable()

		self.label = None
		self._load_label()

		self.inp_seq = []  # 所有序列id的embedding  [6, 90W, max_seq_len, embed_size]
		self._load_seq_inp()  # 加载所有序列 的 embedding
		self.inp_last_idx = np.array([i.shape[0] for i in self.inp_seq[0]]) - 1   # 所有序列的最后一位索引

		assert self.label.shape[0]==self.inp_last_idx.shape[0]

		self.len = self.label.shape[0]   # 数据长度
		div, mod = divmod(self.len, self.batch_size)
		self.n_batch = div + min(mod, 1)   # 最大batch数

		self.yield_idx = np.arange(self.len)  # 数据索引
		if self.shuffle: np.random.shuffle(self.yield_idx)  # shuffle

	def _load_label(self):  # 加载数据标签
		with open(self.label_artifact_path, 'rb') as f:
			self.label = np.load(f)

	def _load_seq_inp(self):  # 加载word2Vec向量
		for target, path in zip(self.seq_inp_target, self.seq_inp_path):
			w2v_model =  Word2Vec.load(self.w2v_registry[target])
			if self.logger: self.logger.info('{} w2v model is loaded'.format(target.capitalize()))
			with open(path, 'rb') as f:
				seq_list = pickle.load(f)
			self.inp_seq.append([torch.from_numpy(np.stack([w2v_model.wv[item] for item in seq[:self.max_seq_len]], axis=0)).float() for seq in seq_list])

			del w2v_model, seq_list
			_ = gc.collect()
			if self.logger: self.logger.info('{} embedded sequence is ready'.format(target.capitalize()))

	def __len__(self):
		return self.label.shape[0]

	def __iter__(self):
		self.cur_batch = 0
		return self

	def __next__(self):
		if self.cur_batch >= self.n_batch:
			raise StopIteration
		else:  # 每次读取一个batch
			if self.logger: self.logger.info('Yielding batch {}/{}'.format(self.cur_batch+1, self.n_batch))
			cur_index = self.yield_idx[self.cur_batch*self.batch_size:(self.cur_batch+1)*self.batch_size]
			y = self.label[cur_index]
			x_seq = [torch.nn.utils.rnn.pad_sequence([seq[i] for i in cur_index], batch_first=True, padding_value=0) for seq in self.inp_seq]
			x_seq_last_idx = self.inp_last_idx[cur_index]
			self.cur_batch += 1
			return y, x_seq, x_seq_last_idx   # x_seq表示6种序列, [6, batch_size, max_seq_len, embed_size]

class test_data_loader(object):
	"""
	Load test input
	"""
	def __init__(self, seq_inp_target, seq_inp_path, w2v_registry, max_seq_len=100, batch_size=512, logger=None):
		"""
		: seq_inp_target (list[str])): list of embedding variables
		: seq_inp_path (list[str])): list of paths to a pkl file 
		: w2v_registry (dict): key is the embedded variable and value is the path to a gensim.models.Word2Vec artifact
		: max_seq_len (int): max length for sequence input, default 100 
		: batch_size (int): batch size for yielding data

		Sample code
		```python
		seq_inp_target = ['product', 'creative']
		seq_inp_path = ['/Users/ywu/Desktop/product_toy.pkl', '/Users/ywu/Desktop/creative_toy.pkl']
		w2v_registry = {
			"product": "/Users/ywu/Desktop/Tencent-Ads-Algo-Comp-2020/Script/embed_artifact/product_embed_s128_j1j5w652", 
			"creative": "/Users/ywu/Desktop/Tencent-Ads-Algo-Comp-2020/Script/embed_artifact/creative_embed_s256_5y76t_gp"
		}

		test_loader = test_data_loader(seq_inp_target, seq_inp_path, w2v_registry)
		test_iterator = iter(train_loader)
		while True:
			try:
				x_seq, x_last_idx = next(test_iterator)
				...
			except:
				break
		del test_iterator, test_loader
		_ = gc.collect()
		```
		"""
		assert isinstance(seq_inp_target, list), isinstance(seq_inp_path, list) and isinstance(w2v_registry, dict)
		assert all([k in w2v_registry for k in seq_inp_target]) and all([v.split('.')[-1]=='pkl' for v in seq_inp_path])
		self.seq_inp_target = seq_inp_target
		self.seq_inp_path = seq_inp_path
		self.w2v_registry = w2v_registry
		self.max_seq_len = max_seq_len
		self.batch_size = batch_size
		self.logger = logger

		if not gc.isenabled(): gc.enable()

		self.inp_seq = []
		print("load seq_input")
		self._load_seq_inp()
		self.inp_last_idx = np.array([i.shape[0] for i in self.inp_seq[0]]) - 1

		self.len = self.inp_last_idx.shape[0]
		div, mod = divmod(self.len, self.batch_size)
		self.n_batch = div + min(mod, 1)

		self.yield_idx = np.arange(self.len)

	def _load_seq_inp(self):
		for target, path in zip(self.seq_inp_target, self.seq_inp_path):
			w2v_model =  Word2Vec.load(self.w2v_registry[target])
			if self.logger: self.logger.info('{} w2v model is loaded'.format(target.capitalize()))
			with open(path, 'rb') as f:
				seq_list = pickle.load(f)
			self.inp_seq.append([torch.from_numpy(np.stack([w2v_model.wv[item] for item in seq[:self.max_seq_len]], axis=0)).float() for seq in seq_list])

			del w2v_model, seq_list
			_ = gc.collect()
			if self.logger: self.logger.info('{} embedded sequence is ready'.format(target.capitalize()))

	def __len__(self):
		return self.inp_last_idx.shape[0]

	def __iter__(self):
		self.cur_batch = 0
		return self

	def __next__(self):
		if self.cur_batch >= self.n_batch:
			raise StopIteration
		else:
			if self.logger: self.logger.info('Yielding batch {}/{}'.format(self.cur_batch+1, self.n_batch))
			cur_index = self.yield_idx[self.cur_batch*self.batch_size:(self.cur_batch+1)*self.batch_size]
			x_seq = [torch.nn.utils.rnn.pad_sequence([seq[i] for i in cur_index], batch_first=True, padding_value=0) for seq in self.inp_seq]
			x_seq_last_idx = self.inp_last_idx[cur_index]
			self.cur_batch += 1
			return x_seq, x_seq_last_idx
