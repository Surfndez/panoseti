#! /usr/bin/env python3

"""
A script for finding the pairs of pulse height frames from two modules that
differ by no more than a specified number of nanoseconds.
"""

import sys
import os
import json
from collections import deque
import numpy as np
import matplotlib.pyplot as plt


sys.path.append('../util')
import pff
sys.path.append('../control')
import config_file

# Default data
DATA_IN_DIR = '/Users/nico/Downloads/720_ph_12pe'
DATA_OUT_DIR = '.'


#fname_a = 'start_2022-07-20T06_44_48Z.dp_ph16.bpp_2.dome_0.module_1.seqno_0.pff' # astrograph 1
#fname_b = 'start_2022-07-20T06_44_48Z.dp_ph16.bpp_2.dome_0.module_254.seqno_0.pff' # astrograph 2
#fname_b = 'start_2022-07-20T06_44_48Z.dp_ph16.bpp_2.dome_0.module_3.seqno_0.pff' # nexdome

# July 20
fname_b = 'start_2022-07-21T06_03_03Z.dp_ph16.bpp_2.dome_0.module_1.seqno_0.pff' # astrograph 1
fname_a = 'start_2022-07-21T06_03_03Z.dp_ph16.bpp_2.dome_0.module_254.seqno_0.pff' # astrograph 2
#fname_b = 'start_2022-07-21T06_03_03Z.dp_ph16.bpp_2.dome_0.module_3.seqno_0.pff' # nexdome

fpath_a = f'{DATA_IN_DIR}/{fname_a}'
fpath_b = f'{DATA_IN_DIR}/{fname_b}'


'''
def get_module_file(module_ip_addr):
    parsed = pff.parse_name(fname)
    mod_num = parsed['module']
'''


def get_pkt_timestamp(frame):
    """Returns the pkt timestamp of frame."""
    pkt_utc = frame[1]['pkt_utc']
    pkt_nsec = frame[1]['pkt_nsec']
    return pkt_utc * 10**9 + pkt_nsec


def get_timestamp(frame):
    """Returns a timestamp for frame."""
    tv_sec = frame[1]['tv_sec']
    pkt_nsec = frame[1]['pkt_nsec']
    return tv_sec * 10**9 + pkt_nsec


def get_timestamp_ns_diff(a, b):
    """Returns a tuple (diff in pkt_utc, diff in pkt_nsec)."""
    a_time, b_time = get_timestamp(a), get_timestamp(b)
    return a_time - b_time


def is_coincident(a, b, max_time_diff):
    """Returns True iff the absolute difference between the timestamps
    of a and b is less than or equal to max_time_diff."""
    within_threshold = abs(get_timestamp_ns_diff(a, b)) <= max_time_diff
    return within_threshold


def a_after_b(a, b):
    """Returns True iff the timestamp of a is greater than the timestamp of b."""
    diff = get_timestamp_ns_diff(a, b)
    return diff > 0


def get_next_frame(file_obj, frame_num):
    # Get the next frame from module A
    j, img = None, None
    try:
        j = pff.read_json(file_obj)
        j = json.loads(j.encode())
        img = pff.read_image(file_obj, 16, 2)
    except Exception as e:
        # Deal with EOF issue pff.read_json
        if repr(e)[:26] == "Exception('bad type code',":
            return None
    if not j or not img:
        return None
    frame = (frame_num, j, img)
    return frame


def search(a_path, b_path, max_time_diff, threshold_pe):
    """
    Identify all pairs of frames from the files a_path and b_path with timestamps that
    differ by no more than 100ns.
    Assumes that the timestamps in each ph file are monotonically increasing when read from top to bottom.
    Returns a list of coincident frame pairs.
    """
    pairs = list()
    a_frame_num, b_frame_num = 0, 0
    b_deque = deque()

    def b_deque_right_append_next_frame(b_file_obj):
        nonlocal b_frame_num
        b_frame = get_next_frame(b_file_obj, b_frame_num)
        if b_frame is not None:
            b_deque.append(b_frame)
            b_frame_num += 1

    with open(a_path, 'rb') as fa, open(b_path, 'rb') as fb:
        b_deque_right_append_next_frame(fb)
        while True:
            print(f'Module A: processed up to frame {a_frame_num:,}... ', end='')
            # Get the next frame for module A and check if we've reached EOF.
            a_frame = get_next_frame(fa, a_frame_num)
            if a_frame is None:
                break
            # Left pop b_deque until a coincident frame is found.
            while len(b_deque) > 0 \
                    and a_after_b(a_frame, b_deque[0]) \
                    and not is_coincident(a_frame, b_deque[0], max_time_diff):
                b_deque.popleft()
                # Right append frames if b_deque runs out of frames.
                if len(b_deque) == 0:
                    b_deque_right_append_next_frame(fb)
            # Check frames that appear after b_deque[0] until a non-coincident frame is found.
            right_index = 0
            while right_index < len(b_deque) and is_coincident(a_frame, b_deque[right_index], max_time_diff):
                # Each coincident pair of frames is added to the list pairs.
                frame_pair = a_frame, b_deque[right_index]
                if frame_pair in pairs:
                    print(f'duplicate frame pair: \n\t{frame_pair[0]}\n\t{frame_pair[1]}')
                pairs.append(frame_pair)
                right_index += 1
                if right_index >= len(b_deque):
                    b_deque_right_append_next_frame(fb)
            a_frame_num += 1
            print('\r', end='')
    print('Done!')
    return pairs


def get_image_2d(image_1d):
    """Converts a 1x256 element array to a 16x16 array."""
    rect = np.zeros((16,16,))
    for row in range(16):
        for col in range(16):
            rect[row][col] = image_1d[16 * row + col]
    return rect


def style_fig(fig, fname_a, fname_b, max_time_diff, fig_num):
    # Configure each figure
    parsed_a, parsed_b = pff.parse_name(fname_a), pff.parse_name(fname_b)
    title = f"Pulse Height Event from Module {parsed_a['module']} and Module {parsed_b['module']} within {max_time_diff:,} ns"
    title += f"\nLeft: Dome: {parsed_a['dome']}, Module {parsed_a['module']}; Start: {parsed_a['start']}; Seq No: {parsed_a['seqno']}"
    title += f"\nRight: Dome: {parsed_b['dome']}, Module {parsed_b['module']}; Start: {parsed_b['start']}; Seq No: {parsed_b['seqno']}"
    fig.suptitle(title)
    fig.tight_layout()
    canvas = fig.canvas
    canvas.manager.set_window_title(f'Figure {fig_num:,}')
    canvas.get_default_filename = \
        lambda: f"start_{parsed_b['start']}.dome_{parsed_a['dome']}.module_{parsed_a['module']}.seqno_{parsed_a['seqno']}" \
                + f"__dome_{parsed_a['dome']}.module_{parsed_a['module']}.seqno_{parsed_a['seqno']}" + \
                f".fignum_{fig_num}.{canvas.get_default_filetype()}"


def style_ax(fig, ax, frame, plot):
    ax.set_box_aspect(1)
    metadata_text = 'Mod {0}, Quabo {1}: pkt_num={2}, \npkt_utc={3}, pkt_nsec={4},\n tv_sec={5}, tv_usec={6}'.format(
        frame[1]['mod_num'], frame[1]['quabo_num'], frame[1]['pkt_num'], frame[1]['pkt_utc'],
        frame[1]['pkt_nsec'], frame[1]['tv_sec'], frame[1]['tv_usec'])
    ax.set_title(metadata_text)
    cbar = fig.colorbar(plot, ax=ax, fraction=0.035, pad=0.05)
    cbar.ax.get_yaxis().labelpad = 15
    cbar.ax.set_ylabel('Photoelectrons (Raw ADC)', rotation=270)


def plot_frame(fig, ax, frame):
    frame_img = get_image_2d(frame[2])
    plot = ax.pcolormesh(np.arange(16), np.arange(16), frame_img)
    style_ax(fig, ax, frame, plot)


def plot_coincidence(a, b, max_time_diff, fig_num):
    fig, axs = plt.subplots(1, 2, figsize=(15, 8))
    for ax, frame in zip(axs, [a, b]):
        plot_frame(fig, ax, frame)
    style_fig(fig, fname_a, fname_b, max_time_diff, fig_num)
    plt.show()


def do_search():
    max_time_diff = 100
    pairs = sorted(search(fpath_a, fpath_b, max_time_diff, 0))
    if len(pairs) == 0:
        print(f'No coincident frames found within {max_time_diff:,} ns of each other.')
        sys.exit(0)
    do_plot = input(f'Plot {len(pairs)} figures? (Y/N): ')
    if do_plot.lower() == 'y':
        for fig_num, pair in enumerate(pairs):
            print(f'\nFigure {fig_num:,}:')
            mod_a, mod_b = pair[0], pair[1]
            print(f'Left module: {mod_a[1]}\nRight module : {mod_b[1]}')
            plot_coincidence(mod_a, mod_b, max_time_diff, fig_num)
            fig_num += 1


if __name__ == '__main__':
    do_search()
    #check_order(fpath_a)