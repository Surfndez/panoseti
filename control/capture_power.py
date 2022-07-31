#! /usr/bin/env python3

"""
Script for capturing metadata from each ethernet outlet
and storing it in the Redis database.
"""
from datetime import datetime
import time

import config_file
import power
import redis_utils

# Time between updates.
UPDATE_INTERVAL = 1


def get_ups_fields(ups_dict):
    """Creates a dictionary of values to write into Redis."""
    power_status = "ON" if power.quabo_power_query(ups_dict) else "OFF"
    rkey_fields = {
        'Computer_UTC': time.time(),
        'POWER': power_status
    }
    return rkey_fields


def get_ups_rkey(ups_key):
    ups_name = ups_key[3:]
    if ups_name[0] == '_':
        ups_name = ups_name[1:]
    if ups_name:
        ups_rkey = f'UPS_{ups_name.upper()}'
    else:
        ups_rkey = 'UPS_0'
    return ups_rkey


def main():
    r = redis_utils.redis_init()
    obs_config = config_file.get_obs_config()
    ups_keys = [key for key in obs_config.keys() if 'ups' in key.lower()]
    print("capture_power.py: Running...")
    while True:
        for ups_key in ups_keys:
            rkey = get_ups_rkey(ups_key)
            ups_dict = obs_config[rkey]
            fields = get_ups_fields(ups_dict)
            redis_utils.store_in_redis(r, rkey, fields)
        time.sleep(UPDATE_INTERVAL)


if __name__ == "__main__":
    #main()
    ...
