import numpy as np
import librosa
import os
import pickle
import gzip
import sys

'''
functions to preprocess audio i.e. extract features for classification
uses a log-power CQT encoded into a uint16 numpy matrix to save space
contains both pyspark functions for running on clusters/multiple threads
and vanilla python functions
'''

def feature_extract(songfile_name):
	'''
	takes: filename
	outputs: audio feature representation from that file (currently cqt)
	**assumes working directory contains raw song files**
	returns a tuple containing songfile name and numpy array of song features
	'''
	song_loc = os.path.abspath(songfile_name)
	y, sr = librosa.load(song_loc)
	desire_spect_len = 2580
	C = librosa.cqt(y=y, sr=sr, hop_length=512, fmin=None,
					n_bins=84, bins_per_octave=12, tuning=None,
					filter_scale=1, norm=1, sparsity=0.01, real=False)
	# get log-power spectrogram with noise floor of -80dB
	C = librosa.logamplitude(C**2)
	# scale log-power spectrogram to positive integer value for smaller footpint
	noise_floor_db = 80
	scaling_factor = (2**16 - 1)/noise_floor_db
	C += noise_floor_db
	C *= scaling_factor
	C = C.astype('uint16')
	# if spectral respresentation too long, crop it, otherwise, zero-pad
	if C.shape[1] >= desire_spect_len:
	    C = C[:,0:desire_spect_len]
	else:
		C = np.pad(C,((0,0),(0,desire_spect_len-C.shape[1])), 'constant')
	return songfile_name, C

'''
vanilla python functions
'''

def create_feature_matrix(song_folder):
	'''
	takes: song folder filled with mp3 files as input
	outputs: key-value pairs of filenames : feature representations (spectrograms)
    list of filenames that caused exceptions
	'''
	feature_matrix = {}
	exceptions = []
	for filename in os.listdir(song_folder):
		if filename.endswith(".mp3"):
			try:
				print("Processing: ", filename, end="\r")
				name, features = feature_extract(os.path.join(song_folder,filename))
				feature_matrix[name] = features
			except:
				print("Exception on: ", filename)
				exceptions.append(filename)
	return feature_matrix, exceptions

def save_feature_matrix(song_folder,save_path):
	fm,excepts = create_feature_matrix(song_folder)
	fileHandle = gzip.open(save_path, "wb")
	pickle.dump(fm, fileHandle)
	fileHandle.close()

'''
pyspark functions 
'''

def create_feature_matrix_spark(song_folder):
	# cqt wrapper
	def log_cqt(y,sr):
		C =  librosa.cqt(y=y, sr=sr, hop_length=512, fmin=None, 
		n_bins=84, bins_per_octave=12, tuning=None,
		filter_scale=1, norm=1, sparsity=0.01, real=True)
		# get log-power spectrogram with noise floor of -80dB
		C = librosa.logamplitude(C**2)
		# scale log-power spectrogram to positive integer value for smaller footpint
		noise_floor_db = 80
		scaling_factor = (2**16 - 1)/noise_floor_db
		C += noise_floor_db
		C *= scaling_factor
		C = C.astype('uint16')
		return C
	# padding wrapper
	def padding(C,desired_spect_len):
		if C.shape[1] >= desired_spect_len:
			C = C[:,0:desired_spect_len]
		else:
			C = np.pad(C,((0,0),(0,desired_spect_len-C.shape[1])), 'constant')
		return C
	# load try-catch wrapper
	def try_load(filename):
		try:
			sys.stdout.write('Processing: %s \r' % os.path.basename(filename))
			sys.stdout.flush()
			return librosa.load(filename)
		except:
			pass
	# transormations
	filesRDD = sc.parallelize([os.path.join(song_folder,filename) for filename in os.listdir(song_folder) if filename.endswith(".mp3")])
	rawAudioRDD = filesRDD.map(lambda x: (os.path.basename(x),try_load(x))).filter(lambda x: x[1] != None)
	rawCQT = rawAudioRDD.map(lambda x: (x[0], log_cqt(x[1][0],x[1][1])))
	paddedCQT = rawCQT.map(lambda x: (x[0],padding(x[1],2580)))
	return paddedCQT.collect()

def save_feature_matrix_spark(song_folder,save_path):
	fm,excepts = create_feature_matrix_spark(song_folder)
	fm = {i[0]:i[1] for i in fm}
	fileHandle = gzip.open(save_path, "wb")
	pickle.dump(fm, fileHandle)
	fileHandle.close()

# cluster
song_folder = '/scratch/mss460/shs/shs_train'
save_path = '/home/mss460/training_set_cqt.pickle'
# hadoop song folder
hadoop_song_folder = '/user/mss460/shs/shs_train'

# local
song_folder = '/Volumes/Amelia_Red_2TB/shs/shs_train'
save_path = '/Volumes/Amelia_Red_2TB/shs/training_set_cqt.pickle'
