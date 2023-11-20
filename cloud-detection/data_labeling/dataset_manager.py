#! /usr/bin/env python3

"""
DatasetManager is designed to perform the following tasks:
    - Aggregate data labels produced by users into a single main dataframe.
    - Collect and organize all requisite features into a training set ready for ingestion by an ML model.
"""

import sys
import os
import json
import shutil

import pandas as pd

from batch_building_utils import *
from dataframe_utils import *
from dataset_utils import *
from pano_builder import PanoBatchBuilder

sys.path.append('../../util')
#from pff import parse_name

class DatasetManager:

    def __init__(self, task='cloud-detection'):
        self.task = task
        self.dataset_dir = get_root_dataset_dir(task)
        self.label_log_path = f'{self.dataset_dir}/{label_log_fname}'
        self.user_labeled_path = f'{self.dataset_dir}/{user_labeled_dir}'
        self.batch_data_array_path = f'{self.dataset_dir}/{batch_data_array_dir}'

        self.main_dfs = {   # Aggregated metadata datasets.
            'user': pd.DataFrame,
            'skycam': pd.DataFrame,
            'pano': pd.DataFrame,
            'feature': pd.DataFrame,
            'labeled': pd.DataFrame,
            'dataset-labels': pd.DataFrame,
            'user-batch-log': pd.DataFrame
        }
        self.init_dataset_dir()


    def init_dataset_dir(self):
        """
        Initialize dataset directory only if it does not exist
            - Create label_log file
            - Init dataframes
        """
        # Make dataset_dir
        os.makedirs(self.dataset_dir, exist_ok=True)
        os.makedirs(self.user_labeled_path, exist_ok=True)
        os.makedirs(self.batch_data_array_path, exist_ok=True)
        self.init_main_dfs()

    def get_main_df_save_name(self, df_type):
        """Get standard main_df filename."""
        save_name = "type_{0}".format(df_type)
        return save_name + '.csv'

    def init_main_dfs(self):
        """Initialize the aggregated dataframes for the main dataset."""
        if isinstance(self, CloudDetectionDatasetBuilder):
            # Make empty dataframes from standard format function
            for df_type in self.main_dfs:
                self.main_dfs[df_type] = get_dataframe(df_type)  # Create df using standard definition
                self.save_main_df(df_type)
        else:
            for df_type in self.main_dfs:
                self.main_dfs[df_type] = self.load_main_df(df_type)
                if self.main_dfs[df_type] is None:
                    raise ValueError(f"Dataframe for '{df_type}' missing in dataset directory!")

    def load_main_df(self, df_type):
        """Load the main dataset dataframes."""
        df_path = f'{self.dataset_dir}/{self.get_main_df_save_name(df_type)}'
        if not os.path.exists(df_path):
            raise FileNotFoundError(f'{df_path} does not exist!')
        with open(df_path, 'r') as f:
            df = pd.read_csv(f, index_col=0)
            return df

    def save_main_df(self, df_type, overwrite_ok=True):
        """Save the main dataset dataframes."""
        df_path = f'{self.dataset_dir}/{self.get_main_df_save_name(df_type)}'
        df = self.main_dfs[df_type]
        if os.path.exists(df_path) and not overwrite_ok:
            raise FileNotFoundError(f'{df_path} exists and overwrite_ok=False. Aborting save...')
        with open(df_path, 'w'):
            df.to_csv(df_path)


class CloudDetectionDatasetBuilder(DatasetManager):
    def __init__(self):
        self.task = 'cloud-detection'
        super().__init__(task=self.task)
        # Proportion of labelers that must agree on label for each example to be included in dataset:
        # self.
        self.agreement_threshold = 0.5
        self.labeled_batches = self.get_labeled_batches()

    """Manage user-produced data"""
    def unpack_user_labeled_batches(self):
        for batch_name in os.listdir(self.user_labeled_path):
            if batch_name.endswith('.zip'):
                batch_zipfile_path = f'{self.user_labeled_path}/{batch_name}'
                shutil.unpack_archive(batch_zipfile_path, batch_zipfile_path[:-4], format='zip')
                os.remove(batch_zipfile_path)

    def get_labeled_batches(self):
        """Return list of available user-labeled data batches."""
        labeled_batches = []
        if os.path.exists(self.user_labeled_path):
            self.unpack_user_labeled_batches()
            for batch_name in os.listdir(self.user_labeled_path):
                if not batch_name.startswith('task_'):
                    continue
                parsed = parse_name(batch_name)
                if parsed['task'] != self.task:
                    raise ValueError(f"Found data with a task={parsed['task']}, "
                                     f"which does not match the task of this dataset: {self.task}")
                labeled_batches.append(batch_name)
        return labeled_batches


    def majority_vote_agg(self, x):
        y = x.value_counts(normalize=True)
        majority_label = y.index[0]
        prop_of_votes_for_maj_label = y[0]
        if prop_of_votes_for_maj_label >= self.agreement_threshold and majority_label != 'unsure':
            return majority_label
        return None

    def add_user(self, batch_name, user_uid):
        # If user not tracked in user_df, add them here.
        user_df = self.main_dfs['user']
        if user_uid not in user_df['user_uid']:
            user_info_fname = f"{self.user_labeled_path}/{batch_name}/user_info.json"
            with open(user_info_fname, "r") as f:
                user_info = json.load(f)
                user_df = add_user(user_df, user_uid, user_info['name'])
        self.main_dfs['user'] = user_df
        self.save_main_df('user')

    def aggregate_labeled_data(self):
        """Incorporate each new user-labeled data batch into the dataset."""
        ubl_df = self.main_dfs['user-batch-log']
        lbd_df = self.main_dfs['labeled']
        for path in self.labeled_batches:
            parsed = parse_name(path)
            user_uid, batch_id = parsed['user-uid'], int(parsed['batch-id'])

            self.add_user(path, user_uid)

            batches_labeled_by_user = ubl_df.loc[ubl_df['user_uid'] == user_uid, 'batch_id']
            if batch_id in batches_labeled_by_user:
                continue
            # Check if data batch has a complete set of labels
            user_unlabeled_df = load_df(
                user_uid, batch_id, 'unlabeled', task=self.task, is_temp=False,
                save_dir=get_data_export_dir(self.task, batch_id, user_uid, self.user_labeled_path)
            )
            if len(user_unlabeled_df[user_unlabeled_df.is_labeled == False]) > 0:
                print(f'Some data in "{path}" are missing labels --> '
                      f'Skipping this batch for now.')
                continue
            ubl_df = add_user_batch_log(ubl_df, user_uid, batch_id)
            user_labeled_df = load_df(
                user_uid, batch_id, 'labeled', task=self.task, is_temp=False,
                save_dir=get_data_export_dir(self.task, batch_id, user_uid, self.user_labeled_path)
            )

            # Concat new labeled data to existing labeled data
            lbd_df = pd.concat([lbd_df, user_labeled_df], ignore_index=True, verify_integrity=True)
        # Save dfs at end to ensure all updates are successful before write.
        grouped = lbd_df.groupby('feature_uid', as_index=False)
        dsl_df = grouped[['label']].agg(self.majority_vote_agg)
        dsl_df = dsl_df.loc[~dsl_df.label.isna()]

        self.main_dfs['labeled'] = lbd_df
        self.main_dfs['dataset-labels'] = dsl_df
        self.main_dfs['user-batch-log'] = ubl_df

        self.save_main_df('dataset-labels')
        self.save_main_df('labeled')
        self.save_main_df('user-batch-log')

    """Aggregate batch metadata"""

    def aggregate_batch_data_features(self, batch_id):
        batch_data_path = f'{batch_data_root_dir}/{get_batch_dir(self.task, batch_id)}'
        for df_type in ['pano', 'skycam', 'feature']:
            df = load_df(
                None, batch_id, df_type, self.task,
                is_temp=False, save_dir=batch_data_path
            )
            if df is None:
                raise ValueError(f"Dataframe for '{df_type}' missing in batch directory!")
            self.main_dfs[df_type] = pd.concat([df, self.main_dfs[df_type]], ignore_index=True, verify_integrity=True)
            self.main_dfs[df_type] = self.main_dfs[df_type].loc[~self.main_dfs[df_type].duplicated()]
            # Save dfs at end to ensure all updates are successful before write.
            self.save_main_df(df_type)

    def verify_pano_feature_data(self, batch_id):
        """Returns True iff all data files for labeled pano_features exist and are not empty."""
        ftr_df = self.main_dfs['feature']
        dsl_df = self.main_dfs['dataset-labels']
        pano_df = self.main_dfs['pano']
        labeled_feature_uids = dsl_df.loc[:, 'feature_uid']
        all_valid = True
        for feature_uid in labeled_feature_uids:
            pano_uid = ftr_df.loc[ftr_df['feature_uid'] == feature_uid, 'pano_uid'].iloc[0]
            run_dir = pano_df.loc[pano_df['pano_uid'] == pano_uid, 'run_dir'].iloc[0]
            pano_dataset_path = get_pano_dataset_path(self.task, batch_id, run_dir)
            for img_type in PanoDatasetBuilder.supported_img_types:
                pano_feature_path = get_pano_dataset_feature_path(pano_dataset_path, pano_uid, img_type)
                all_valid &= os.path.exists(pano_feature_path)
                all_valid &= os.path.getsize(pano_feature_path) > 0
        return all_valid


    def generate_dataset(self):
        print("Aggregating user labels")
        self.aggregate_labeled_data()
        ubl_df = self.main_dfs['user-batch-log']
        batch_ids = ubl_df.groupby('batch_id')['batch_id'].unique()
        print("Aggregating feature metadata")
        for batch_id in batch_ids.iloc[0]:
            self.aggregate_batch_data_features(batch_id)
            if not self.verify_pano_feature_data(batch_id):
                raise ValueError('Not all pano features are valid!')
        print("Done")

    def export_dataset(self):
        # TODO
        pass



if __name__ == '__main__':
    test = DatasetManager()
    test.update_dataset()

