#! /usr/bin/env python3
# Visit https://mthamilton.ucolick.org/data/ and download archived skycam
# images at a specified date
import time
from datetime import datetime, timedelta, tzinfo
import os
import tarfile
import shutil

from selenium import webdriver
from selenium.webdriver.common.by import By


from skycam_utils import get_skycam_dir, get_skycam_subdirs, is_data_downloaded, get_skycam_img_time


def get_skycam_link(skycam_type, year, month, day):
    """
    Skycam link formats
      0 = 4 digit year
      1 = 2 digit month
      2 = 2 digit day, 1-indexed
    """
    if skycam_type == 'SC':
        return f'https://mthamilton.ucolick.org/data/{year}-{month:0>2}/{day:0>2}/allsky/public/'
    elif skycam_type == 'SC2':
        return f'https://mthamilton.ucolick.org/data/{year}-{month:0>2}/{day:0>2}/skycam2/public/'



def download_wait(directory, timeout, nfiles=None, verbose=False):
    """
    Wait for downloads to finish with a specified timeout.

    Args
    ----
    directory : str
        The path to the folder where the files will be downloaded.
    timeout : int
        How many seconds to wait until timing out.
    nfiles : int, defaults to None
        If provided, also wait for the expected number of files.

    Code from: https://stackoverflow.com/questions/34338897/python-selenium-find-out-when-a-download-has-completed
    """
    seconds = 0
    dl_wait = True
    last_download_fsizes = {}
    while dl_wait and seconds < timeout:
        time.sleep(1)
        dl_wait = False
        files = os.listdir(directory)
        if nfiles and len(files) != nfiles:
            dl_wait = True

        num_crdownload_files = 0
        for fname in files:
            if fname.endswith('.crdownload'):
                num_crdownload_files += 1
                current_fsize = os.path.getsize(f'{directory}/{fname}')
                if fname in last_download_fsizes:
                    last_fsize = last_download_fsizes[fname]
                    if current_fsize > last_fsize:
                        seconds = 0
                    last_download_fsizes[fname] = current_fsize
                else:
                    last_download_fsizes[fname] = current_fsize

        if num_crdownload_files == 0 and verbose:
            print('Successfully downloaded all files')

        dl_wait = num_crdownload_files > 0
        seconds += 1
    return seconds


def download_skycam_data(skycam_type, year, month, day, verbose, root):
    """
    Downloads all the skycam images collected on year-month-day from 12pm up to 12pm the next day (in PDT).

    @param skycam: 'SC' or 'SC2'
    @param year: 4 digit year,
    @param month: month, 1-indexed
    @param day: day, 1-indexed
    """
    assert len(str(year)) == 4, 'Year must be 4 digits'
    assert 1 <= month <= 12, 'Month must be between 1 and 12, inclusive'
    assert 1 <= day <= 31, 'Day must be between 1 and 31, inclusive'


    # Create skycam directory
    skycam_path = f'{root}/{get_skycam_dir(skycam_type, year, month, day)}'
    os.makedirs(skycam_path, exist_ok=True)

    # Set Chrome driver options
    prefs = {
        'download.default_directory': os.path.abspath(skycam_path)
    }
    #print(os.path.abspath(skycam_dir))
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_experimental_option('prefs', prefs)
    chrome_options.add_argument("--headless")   # Don't open a browser window
    # Open Chrome driver
    driver = webdriver.Chrome(options=chrome_options)

    # Open URL to Lick skycam archive
    link = get_skycam_link(skycam_type, year, month, day)
    driver.get(link)

    # Check if download page exists
    title = driver.title
    if title == '404 Not Found' or title != 'Mt. Hamilton Data Repository':
        print(f"The link '{link}' does not contain valid skycam data. Exiting...")
        driver.close()
        shutil.rmtree(skycam_path)
        return None

    # Select all files to download
    select_all_button = driver.find_element(By.LINK_TEXT, "all")
    select_all_button.click()

    # Deselect movie files
    # These are always the first two checkboxes
    movie_checkboxes = driver.find_elements(By.XPATH, "//input[@type='checkbox']")
    for i in range(2):
        movie_checkboxes[i].click()

    # Download tarball file to out_dir
    if verbose: print(f'Downloading data from {link}')
    download_tarball = driver.find_element(By.XPATH, "//input[@type='submit']")
    download_tarball.click()

    download_wait(directory=skycam_path, timeout=30, nfiles=1, verbose=verbose)
    driver.close()

    return skycam_path


def unzip_images(skycam_dir):
    """Unpack image files from tarball."""
    img_subdirs = get_skycam_subdirs(skycam_dir)
    downloaded_fname = ''

    for fname in os.listdir(skycam_dir):
        if fname.endswith('.tar.gz'):
            downloaded_fname = fname
    if downloaded_fname:
        downloaded_fpath = f'{skycam_dir}/{downloaded_fname}'
        with tarfile.open(downloaded_fpath, 'r') as tar_ref:
            tar_ref.extractall(skycam_dir)
        os.remove(downloaded_fpath)

        for path in os.listdir(skycam_dir):
            if os.path.isdir(f'{skycam_dir}/{path}') and path.startswith('data'):
                os.rename(f'{skycam_dir}/{path}', img_subdirs['original'])
    

def remove_day_images(skycam_dir, morning_hour=4, evening_hour=21):
    """Remove skycam images taken between morning_hour and evening_hour."""
    img_subdirs = get_skycam_subdirs(skycam_dir)
    PST_offset = timedelta(hours=-7)
    for skycam_img_fname in sorted(os.listdir(img_subdirs['original'])):
        pst_time = get_skycam_img_time(skycam_img_fname) + PST_offset
        if morning_hour <= pst_time.hour <= evening_hour:
            os.remove("{0}/{1}".format(img_subdirs['original'], skycam_img_fname))

def filter_images(skycam_dir: str, first_t: datetime, last_t: datetime):
    """Remove skycam images between t_start and t_end."""
    img_subdirs = get_skycam_subdirs(skycam_dir)
    for skycam_img_fname in sorted(os.listdir(img_subdirs['original'])):
        skycam_t = get_skycam_img_time(skycam_img_fname)
        if not (first_t <= skycam_t <= last_t):
            os.remove("{0}/{1}".format(img_subdirs['original'], skycam_img_fname))


def download_night_skycam_imgs(skycam_type, year, month, day, first_t, last_t, root, verbose=False):
    skycam_dir = download_skycam_data(skycam_type, year, month, day, verbose, root=root)
    if skycam_dir:
        is_data_downloaded(skycam_dir)
        if verbose: print("Unzipping files...")
        unzip_images(skycam_dir)
        if verbose: print("Removing day images..")
        filter_images(skycam_dir, first_t, last_t)
        return skycam_dir
    else:
        # No valid data found
        return None
 


if __name__ == '__main__':
    download_night_skycam_imgs('SC2', 2023, 10, 13, verbose=True)
