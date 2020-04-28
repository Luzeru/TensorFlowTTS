# -*- coding: utf-8 -*-

# Copyright 2020 Minh Nguyen (@dathudeptrai)
#  MIT License (https://opensource.org/licenses/MIT)

"""Dataset modules."""

from tensorflow_tts.datasets.abstract_dataset import AbstractDataset
from tensorflow_tts.utils import read_hdf5
from tensorflow_tts.utils import find_files

import logging
import os
import random
import itertools
import operator

import numpy as np

import tensorflow as tf
# tf.get_logger().setLevel(logging.ERROR)


class CharactorDurationMelDataset(AbstractDataset):
    """Tensorflow Charactor Mel dataset."""

    def __init__(self,
                 root_dir,
                 charactor_query="*-ids.npy",
                 mel_query="*-norm-feats.npy",
                 duration_query="*-durations.npy",
                 charactor_load_fn=np.load,
                 mel_load_fn=np.load,
                 duration_load_fn=np.load,
                 mel_length_threshold=None,
                 return_utt_id=False
                 ):
        """Initialize dataset.

        Args:
            root_dir (str): Root directory including dumped files.
            charactor_query (str): Query to find charactor files in root_dir.
            mel_query (str): Query to find feature files in root_dir.
            charactor_load_fn (func): Function to load charactor file.
            mel_load_fn (func): Function to load feature file.
            mel_length_threshold (int): Threshold to remove short feature files.
            return_utt_id (bool): Whether to return the utterance id with arrays.

        """
        # find all of charactor and mel files.
        charactor_files = sorted(find_files(root_dir, charactor_query))
        mel_files = sorted(find_files(root_dir, mel_query))
        duration_files = sorted(find_files(root_dir, duration_query))
        # filter by threshold
        if mel_length_threshold is not None:
            mel_lengths = [mel_load_fn(f).shape[0] for f in mel_files]

            idxs = [idx for idx in range(len(mel_files)) if mel_lengths[idx] > mel_length_threshold]
            if len(mel_files) != len(idxs):
                logging.warning(f"Some files are filtered by mel length threshold "
                                f"({len(mel_files)} -> {len(idxs)}).")
            mel_files = [mel_files[idx] for idx in idxs]
            charactor_files = [charactor_files[idx] for idx in idxs]
            duration_files = [duration_files[idx] for idx in idxs]
            mel_lengths = [mel_lengths[idx] for idx in idxs]

            # bucket sequence length trick, sort based-on mel-length.
            idx_sort = np.argsort(mel_lengths)

            # sort
            mel_files = np.array(mel_files)[idx_sort]
            charactor_files = np.array(charactor_files)[idx_sort]
            duration_files = np.array(duration_files)[idx_sort]
            mel_lengths = np.array(mel_lengths)[idx_sort]

            # group
            idx_lengths = [[idx, length] for idx, length in zip(np.arange(len(mel_lengths)), mel_lengths)]
            groups = [list(g) for _, g in itertools.groupby(idx_lengths, lambda a: a[1])]

            # group shuffle
            random.shuffle(groups)

            # get idxs affter group shuffle
            idxs = []
            for group in groups:
                for idx, _ in group:
                    idxs.append(idx)

            # re-arange dataset
            mel_files = np.array(mel_files)[idxs]
            charactor_files = np.array(charactor_files)[idxs]
            duration_files = np.array(duration_files)[idxs]
            mel_lengths = np.array(mel_lengths)[idxs]

        # assert the number of files
        assert len(mel_files) != 0, f"Not found any mels files in ${root_dir}."
        assert len(mel_files) == len(charactor_files) == len(duration_files), \
            f"Number of charactor, mel and duration files are different \
                ({len(mel_files)} vs {len(charactor_files)} vs {len(duration_files)})."

        if ".npy" in charactor_query:
            utt_ids = [os.path.basename(f).replace("-ids.npy", "") for f in charactor_files]

        # set global params
        self.utt_ids = utt_ids
        self.mel_files = mel_files
        self.charactor_files = charactor_files
        self.duration_files = duration_files
        self.mel_load_fn = mel_load_fn
        self.charactor_load_fn = charactor_load_fn
        self.duration_load_fn = duration_load_fn
        self.return_utt_id = return_utt_id

    def get_args(self):
        return [self.utt_ids]

    def generator(self, utt_ids):
        for i, utt_id in enumerate(utt_ids[:4]):
            mel_file = self.mel_files[i]
            charactor_file = self.charactor_files[i]
            duration_file = self.duration_files[i]
            mel = self.mel_load_fn(mel_file)
            charactor = self.charactor_load_fn(charactor_file)
            duration = self.duration_load_fn(duration_file)
            if self.return_utt_id:
                items = utt_id, charactor, duration, mel
            else:
                items = charactor, duration, mel
            yield items

    def create(self,
               allow_cache=False,
               batch_size=1,
               is_shuffle=False,
               map_fn=None,
               reshuffle_each_iteration=True
               ):
        """Create tf.dataset function."""
        output_types = self.get_output_dtypes()
        datasets = tf.data.Dataset.from_generator(
            self.generator,
            output_types=output_types,
            args=(self.get_args())
        )

        if allow_cache:
            datasets = datasets.cache()

        if is_shuffle:
            datasets = datasets.shuffle(
                self.get_len_dataset(), reshuffle_each_iteration=reshuffle_each_iteration)

        datasets = datasets.padded_batch(batch_size, padded_shapes=([None], [None], [None, None]))
        datasets = datasets.prefetch(tf.data.experimental.AUTOTUNE)
        return datasets

    def get_output_dtypes(self):
        output_types = (tf.int32, tf.int32, tf.float32)
        if self.return_utt_id:
            output_types = (tf.dtypes.string, *output_types)
        return output_types

    def get_len_dataset(self):
        return len(self.utt_ids)

    def __name__(self):
        return "CharactorDurationMelDataset"


# if __name__ == "__main__":
#     from tensorflow_tts.models import TFFastSpeech
#     from tensorflow_tts.configs import FastSpeechConfig
#     # def call(
#     #         self,
#     #         input_ids,
#     #         attention_mask,
#     #         speaker_ids,
#     #         duration_gts,
#     #         training=False):
#     fastspeech = TFFastSpeech(config=FastSpeechConfig(), name='fastspeech')
#     optimizer = tf.keras.optimizers.Adam(lr=0.001)

#     datasets = CharactorDurationMelDataset(
#         root_dir="./egs/ljspeech/dump/train/",
#         return_utt_id=False,
#         mel_length_threshold=32,
#     ).create(allow_cache=False, is_shuffle=False, batch_size=4)

#     mel_plot = None

#     @tf.function(experimental_relax_shapes=True)
#     def run_train(data):
#         with tf.GradientTape() as tape:
#             masked_mel_outputs, masked_duration_outputs = fastspeech(
#                 data[0],
#                 attention_mask=tf.math.not_equal(data[0], 0),
#                 speaker_ids=tf.constant([0] * 4),
#                 duration_gts=data[1],
#                 training=True
#             )
#             duration_loss = tf.keras.losses.MeanSquaredError()(
#                 data[1], masked_duration_outputs)
#             mel_loss = tf.keras.losses.MeanSquaredError()(data[2], masked_mel_outputs)
#             loss = duration_loss + mel_loss

#         gradients = tape.gradient(loss, fastspeech.trainable_variables)
#         optimizer.apply_gradients(zip(gradients, fastspeech.trainable_variables))

#         tf.print(duration_loss)
#         # tf.print(masked_duration_outputs)

#         return masked_mel_outputs

#     for _ in range(1000):
#         for data in datasets:
#             pred = run_train(data)

#     fastspeech.summary()
