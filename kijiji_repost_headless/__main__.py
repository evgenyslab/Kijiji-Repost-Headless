import re
import argparse
import os
import sys
import warnings
from time import sleep

import yaml

from kijiji_repost_headless import generate_post_file as generator
from kijiji_repost_headless import kijiji_api

if sys.version_info < (3, 0):
    raise Exception("This program requires Python 3.0 or greater")


def main():
    parser = argparse.ArgumentParser(description="Post ads on Kijiji")
    parser.add_argument('-u', '--username', help='username of your kijiji account')
    parser.add_argument('-p', '--password', help='password of your kijiji account')
    subparsers = parser.add_subparsers(help='sub-command help')
    # the following commands are broken, and are commented out 
    """
    post_parser = subparsers.add_parser('post', help='post a new ad')
    post_parser.add_argument('ad_file', type=str, help='.yml file containing ad details')
    post_parser.set_defaults(function=post_ad)

    show_parser = subparsers.add_parser('show', help='show currently listed ads')
    show_parser.set_defaults(function=show_ads)
    show_parser.add_argument('-k', '--key', dest='sort_key', default='title', choices=['id', 'title', 'rank', 'views'], help="sort ad list by key")
    show_parser.add_argument('-r', '--reverse', action='store_true', dest='sort_reverse', help='reverse sort order')

    delete_parser = subparsers.add_parser('delete', help='delete a listed ad')
    delete_parser.add_argument('ad_file', type=str, help='.yml file containing ad details')
    delete_parser.set_defaults(function=delete_ad)

    nuke_parser = subparsers.add_parser('nuke', help='delete all ads')
    nuke_parser.set_defaults(function=nuke)

    check_parser = subparsers.add_parser('check_ad', help='check if ad is active')
    check_parser.add_argument('ad_file', type=str, help='.yml file containing ad details')
    check_parser.set_defaults(function=check_ad)

    repost_parser = subparsers.add_parser('repost', help='repost an existing ad')
    repost_parser.add_argument('ad_file', type=str, help='.yml file containing ad details')
    repost_parser.set_defaults(function=repost_ad)

    build_parser = subparsers.add_parser('build_ad', help='generates the item.yml file for a new ad')
    build_parser.set_defaults(function=generate_post_file)
    """

    repost_all_parser = subparsers.add_parser('repost_all', help='repost all listed ads')
    repost_all_parser.set_defaults(function=repost_all)

    backup_parser = subparsers.add_parser('backup', help='back up ads to local directory')
    backup_parser.set_defaults(function=back_up)

    repost_backup_parser = subparsers.add_parser('repost_from_backup', help='repost from backup dir')
    repost_backup_parser.set_defaults(function=repost_from_backup)

    args = parser.parse_args()
    print(args.username)
    try:
        args.function(args)
    except argparse.ArgumentError:
        parser.print_help()


def back_up(args, api=None, all_ads_old=None):
    """
    Save all ads locally
    """
    if not api:
        api = kijiji_api.KijijiApi()
        api.login(args.username, args.password)

    if all_ads_old is None:
        all_ads_old = api.get_all_ads()

    if not os.path.isdir('.ads'):
        os.mkdir('.ads')

    user_root = args.username.split('@')[0]

    if not os.path.isdir(os.path.join('.ads', user_root)):
        os.mkdir(os.path.join('.ads', user_root))

    for ad in all_ads_old:
        try:
            ad_bytes = api.scrape_ad(ad)
            write_name = re.sub(r'([\/:?!@#$%<>`\\* ])', '-', ad['ad:title'])
            with open(os.path.join('.ads', user_root, write_name), 'wb') as f:
                f.write(ad_bytes)
        except Exception as e:
            warnings.warn("Could not backup ad: {}".format(ad['ad:title']))


def repost_from_backup(args, api=None):
    if not api:
        api = kijiji_api.KijijiApi()
        api.login(args.username, args.password)

    if not os.path.isdir('.ads'):
        raise FileNotFoundError("ads directory not found")

    user_root = args.username.split('@')[0]

    if not os.path.isdir(os.path.join('.ads', user_root)):
        raise FileNotFoundError("ads USER directory not found")

    ad_files = os.listdir(os.path.join('.ads', user_root))

    if not ad_files:
        raise FileNotFoundError("No ads found in ads dir")

    for ad in ad_files:
        try:
            with open(os.path.join('.ads', user_root, ad), 'rb') as f:
                ad_bytes = f.read()
                api.post_ad_using_data(ad_bytes)
        except Exception as e:
            warnings.warn("Could not repost ad: {} from backup".format(ad))


def repost_all(args, api=None):
    if not api:
        api = kijiji_api.KijijiApi()
        api.login(args.username, args.password)

    all_ads_old = api.get_all_ads()
    # backup:
    back_up(args, api, all_ads_old)
    [api.delete_ad(ad['@id']) for ad in all_ads_old]
    sleep(120)
    [api.post_ad_using_data(api.scrape_ad(ad), []) for ad in all_ads_old]


def get_post_details(ad_file, api=None):
    """
    Extract ad data from inf file
    """
    with open(ad_file, 'r') as f:
        data = yaml.load(f, Loader=yaml.FullLoader)

    files = [open(os.path.join(os.path.dirname(ad_file), picture), 'rb').read() for picture in data['image_paths']]

    # Remove image_paths key; it does not need to be sent in the HTTP post request later on
    del data['image_paths']

    data['postAdForm.title'] = data['postAdForm.title'].strip()

    return [data, files]


def post_ad(args, api=None):
    """
    Post new ad
    """
    [data, image_files] = get_post_details(args.ad_file)
    if not api:
        api = kijiji_api.KijijiApi()
        api.login(args.username, args.password)

    attempts = 1
    while not check_ad(args, api) and attempts < 5:
        if attempts > 1:
            print("Failed ad post attempt #{}, trying again.".format(attempts))
        attempts += 1

        if not api:
            api = kijiji_api.KijijiApi()
            api.login(args.username, args.password)
        api.post_ad_using_data(data, image_files)
    if not check_ad(args, api):
        print("Failed ad post attempt #{}, giving up.".format(attempts))


def show_ads(args, api=None):
    """
    Print list of all ads
    """
    if not api:
        api = kijiji_api.KijijiApi()
        api.login(args.username, args.password)
    all_ads = sorted(api.get_all_ads(), key=lambda k: k[args.sort_key], reverse=args.sort_reverse)

    print("    id    ", "page", "views", "          title")
    [print("{ad_id:10} {rank:4} {views:5} '{title}'".format(
        ad_id=ad['id'],
        rank=ad['rank'],
        views=ad['views'],
        title=ad['title']
    )) for ad in all_ads]


def delete_ad(args, api=None):
    """
    Delete ad
    """
    [data, _] = get_post_details(args.ad_file)

    if not api:
        api = kijiji_api.KijijiApi()
        api.login(args.username, args.password)

    if args.ad_file:
        del_ad_name = ""
        for item in data:
            if item == "postAdForm.title":
                del_ad_name = data[item]
        try:
            api.delete_ad_using_title(del_ad_name)
            print("Deletion successful or unaffected")
        except kijiji_api.KijijiApiException:
            print("Did not find an existing ad with matching title, skipping ad deletion")

def repost_ad(args, api=None):
    """
    Repost ad

    Try to delete ad with same title if possible before reposting new ad
    """
    delete_ad(args, api)

    # Must wait a bit before posting the same ad even after deleting it, otherwise Kijiji will automatically remove it
    print("Waiting 3 minutes before posting again. Please do not exit this script.")
    sleep(60)
    print("Still waiting; 2 more minutes...")
    sleep(60)
    print("Still waiting; 1 minute left...")
    sleep(30)
    print("Still waiting; 30 seconds...")
    sleep(20)
    print("Still waiting; just 10 seconds...")
    sleep(10)
    print("Posting Ad now")
    post_ad(args, api)


def check_ad(args, api=None):
    """
    Check if ad is live
    """
    [data, _] = get_post_details(args.ad_file)

    if not api:
        api = kijiji_api.KijijiApi()
        api.login(args.username, args.password)

    ad_title = ""

    for key, val in data.items():
        if key == "postAdForm.title":
            ad_title = val

    all_ads = api.get_all_ads()
    return [ad['title'] for ad in all_ads if ad['title'] == ad_title]


def nuke(args, api=None):
    """
    Delete all active ads
    """
    if not api:
        api = kijiji_api.KijijiApi()
        api.login(args.username, args.password)
    all_ads = api.get_all_ads()
    [api.delete_ad(ad['id']) for ad in all_ads]


def generate_post_file(args):
    generator.run_program()


if __name__ == "__main__":
    main()
