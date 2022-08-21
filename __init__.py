#!/usr/bin/python
# -*- coding: utf8 -*-
"""
WindowPos

    Simply moves windows around to the target position! Smart enough to know which monitor your window is sitting in 
    and sticks to that monitor!
    
    The idea is to make keyboard shortcuts call this script. e.g. Ctrl + Super + Num9 > top right.
    Useful for any Linux desktop environment with weak window alignment shortcuts.  
    
    Usage:
        
        python __init__.py [position arguments]
        
        e.g. 
            python __init__.py top            Moves window to top of screen
            python __init__.py bottom         Moves window to bottom of screen
            python __init__.py left           Moves window to left of screen
            python __init__.py right          Moves window to right of screen
            python __init__.py top left       Moves window to top left of screen
            python __init__.py bottom left    Moves window to bottom left of screen
            python __init__.py top right      Moves window to top right of screen
            python __init__.py bottom right   Moves window to bottom right of screen
            python __init__.py max            Maximises window to fill whole screen
        

    Derived from these shell commands:
        Get active displays:
        xrandr | grep -w connected

        Get active window details:
        xwininfo -id $(xdotool getactivewindow)
        
        Move active window:
        wmctrl -r :ACTIVE: -b remove,maximized_vert,maximized_horz && wmctrl -r :ACTIVE: -e 0,$target_xoff,$target_yoff,$target_width,$target_height
        
    @author:   Dr Michael J T Brooks
    @date:     2022-08-21
    @version:  20220821
"""

import argparse
import copy
import getpass
import math
import os
import re
import subprocess
import sys
from time import sleep
from subprocess import Popen, PIPE


# How much space on each screen is consumed by always-on-top panels / margins etc. Uses CSS syntax: (top, right, bottom, left)
SCREEN_MARGINS = {
    "DP-0": (0, 0, 24, 0),
    "DP-2": (0, 0, 27, 0),
    "DP-4": (24, 0, 0, 0),
}
CHROMIUM_MARGINS = {
    "DVI-1-0": (32, 0, 32, 0),
    "HDMI-0": (0, 0, 0, 0),
}

# Commands for launching applications of interest -- you may wish to override these!
launcher_commmands = {
    "Brave": "/usr/bin/brave-browser-stable %U",
    "Rambox": "/opt/Rambox/rambox --no-sandbox %U",
    "Spotify": "spotify %U",
    "java": "pycharm",  # Yes this is nasty. That's because PyCharm massively obfuscates its actualy application window.
    "mate-terminal": "mate-terminal"
}


# You can configure presets for a load of windows here. Run this by calling this script with the -l or --layout argument. e.g. -l=dev
layouts = {
    "dev": (
        {"application_name": "Brave", "nth_instance_of_application": 0, "target_monitor_name": "DP-0", "target_desktop_id": 0, "target_position": "right", "spawn_missing": True},
        {"application_name": "mate-terminal", "nth_instance_of_application": 0, "target_monitor_name": "DP-0", "target_desktop_id": 0, "target_position": "left", "spawn_missing": True},
        {"application_name": "java", "nth_instance_of_application": 0, "target_monitor_name": "DP-2", "target_desktop_id": 0, "target_position": "middle", "spawn_missing": True},
        {"application_name": "Spotify", "nth_instance_of_application": 0, "target_monitor_name": "DP-4", "target_desktop_id": 0, "target_position": "left", "spawn_missing": True},
        {"application_name": "Rambox", "nth_instance_of_application": 0, "target_monitor_name": "DP-4", "target_desktop_id": 0, "target_position": "right", "spawn_missing": True},
    )
}


class WindowPositionException(Exception):
    pass


# Regexes
re_dims = re.compile(r"([0-9]+)x([0-9]+)\+([-0-9]+)\+([-0-9]+).*$")
re_win_name = re.compile(r'^.*Window\sid:\s([A-Fa-f0-9]+x[A-Fa-f0-9]+)\s"(.*)".*$', re.MULTILINE)
re_win_x = re.compile(r'^.*Absolute\supper\-left\sX:\s+([0-9]+).*$', re.MULTILINE)
re_win_y = re.compile(r'^.*Absolute\supper\-left\sY:\s+([0-9]+).*$', re.MULTILINE)
re_win_w = re.compile(r'^.*Width:\s+([0-9]+).*$', re.MULTILINE)
re_win_h = re.compile(r'^.*Height:\s+([0-9]+).*$', re.MULTILINE)
re_getwindowgeometry = re.compile(r'^\s+([a-zA-Z\s\d]+):\s?([\-+\d]+)[x|,]([\-+\d]+)(?:\s\(?([a-zA-Z\s\-\d]+):\s*(\d+)+\)?)?')
re_getchildwindowgeometry = re.compile(r'^\s+(0x\d+)\s+"([a-zA-Z-_\d\s]+)":\s+\([a-zA-Z\d\-_:"\s]+\)\s+([\-+\d]+)x([-|+]?\d+)[+|-]-?\d+[+|-]-?\d+\s*([+|-]\d+)([+|-]\d+)')


ACTIVE_WINDOW = ":ACTIVE:"  # Special string used internally to flag when the user is interested in the active window


def get_screens_and_positions():
    """
    Gets all the screens and their positions via Xrandr. This allows us to know where to tile stuff
    :return:
    """
    screens = []
    p_xrandr = Popen(["xrandr"], stdout=PIPE)
    p_mons = Popen(["grep", "-w", "connected"], stdin=p_xrandr.stdout, stdout=PIPE)
    monitor_text, err = p_mons.communicate()

    # Parse the monitors into dicts
    for monitor_line in monitor_text.split("\n"):
        print(monitor_line)
        monitor_dict = {}
        words = monitor_line.split(" ")
        monitor_dict['name'] = words[0]  # First item is ALWAYS the monitor name
        dims = re_dims.findall(monitor_line)
        try:
            dims = dims[0]  # Matches all sit inside a tuple, inside a list!!
        except IndexError:
            # There's no screen on this line!
            pass
        else:
            print(dims)
            monitor_dict["w"] = int(dims[0])
            monitor_dict["h"] = int(dims[1])
            monitor_dict["x"] = int(dims[2])
            monitor_dict["y"] = int(dims[3])
            screens.append(monitor_dict)
    print(screens)
    return screens


def get_window_id_of_active_window():
    """
    Returns the id of an active window
    :return:
    """
    p_xdotool = Popen(["xdotool", 'getactivewindow'], stdout=PIPE)
    active_window, err = p_xdotool.communicate()
    print(active_window)
    if err:
        print("ERROR: {}".format(err))
    return active_window


def cast_safe(item, var_type, *cast_args, **cast_kwargs):
    """
    Cast the item to the type of variable.
    If fails, returns as string.
    Lol... hope this triggers the Java programmers :-D

    :param item:
    :param var_type:
    :return: item as correct type
    """
    try:
        return var_type(item, *cast_args, **cast_kwargs)
    except (ValueError, TypeError) as e:
        print("{}->{}: {}".format(item, var_type, e))
    return str(var_type)


def get_window_geometry(window_id):
    """
    Returns the window geometry of a specific window
    :param window_id:
    :return: {
        "Window": window_id,
        "Position": {
            "x": 150,
            "y": 150,
            "screen": 0
        }
        "Geometry": {
            "w": 1010,
            "h": 598
        }
    }
    """
    window_id = int(window_id)
    p_xdotool = Popen(["xdotool", 'getwindowgeometry', str(window_id)], stdout=PIPE)
    window_geometry, err = p_xdotool.communicate()
    if err:
        print("ERROR: {}".format(err))
    if not window_geometry:
        return {}
    out_info = {}
    lines = window_geometry.split("\n")
    for line in lines:
        line_matches = re_getwindowgeometry.findall(line)
        if not line_matches:
            continue
        try:
            geo_property, x_or_w, y_or_h, supplementary_property, supplementary_property_value = line_matches[0]
        except (IndexError, ValueError) as e:
            print("{}: {}".format(e.__class__.__name__, e))
            continue  # Unparseable line
        geo_property = str(geo_property).strip()
        if str(geo_property).lower().startswith("position"):
            x_term, y_term = "x", "y"
        else:
            x_term, y_term = "w", "h"
        geo_property_dict = {
            x_term: cast_safe(x_or_w, int),
            y_term: cast_safe(x_or_w, int),
        }
        clean_supplementary_property_key = str(supplementary_property).strip()
        if str(supplementary_property).strip():
            geo_property_dict[clean_supplementary_property_key] = cast_safe(supplementary_property_value, int)
        out_info[geo_property] = geo_property_dict
        print(out_info)
    return out_info


def get_children_window_geometry(parent_window_id):
    """
    Gets the geometry of child windows via xwininfo -id 23068752 -children
    :param parent_window_id:
    :return:
    """
    parent_window_id = int(parent_window_id)
    p_xdotool = Popen(["xwininfo", '-id', str(parent_window_id), '-children'], stdout=PIPE, stderr=PIPE)
    children_window_geometry, err = p_xdotool.communicate()
    print(children_window_geometry)
    if err:
        print("ERROR: {}".format(err))
    lines = children_window_geometry.split("\n")
    out_children_window_geometry = []
    for line in lines:
        line_matches = re_getchildwindowgeometry.findall(line)
        if not line_matches:
            continue
        try:
            window_hex_id, window_name, width, height, x_offset, y_offset = line_matches[0]
        except (IndexError, ValueError) as e:
            print("{}: {}".format(e.__class__.__name__, e))
            continue  # Unparseable line
        out_children_window_geometry.append((window_hex_id, width, height))
    return out_children_window_geometry


def filter_to_large_enough_windows(window_ids):
    """
    Return the geometry of large enough windows. Recursive into children by one layer.
    :param window_ids:
    :return: [<id>, <id>]
    """
    print(window_ids)
    WIDTH_THRESHOLD = 200
    HEIGHT_THRESHOLD = 200
    real_windows = []
    for window_id in window_ids:
        window_geo = get_window_geometry(window_id)
        try:
            width = window_geo["Geometry"]["w"]
            height = window_geo["Geometry"]["h"]
        except (KeyError, TypeError, ValueError):
            pass  # Not a real window
        else:
            if width > WIDTH_THRESHOLD and height > HEIGHT_THRESHOLD:
                real_windows.append(window_id)
            else:
                pass
            # Now look at children (just one layer)
            children_window_geometry_list = get_children_window_geometry(window_id)
            for window_hex_id, width, height in children_window_geometry_list:
                if width > WIDTH_THRESHOLD and height > HEIGHT_THRESHOLD:
                    try:
                        window_id_from_hex = int(str(window_hex_id), 16)
                        real_windows.append(window_id_from_hex)
                    except (TypeError, ValueError):
                        pass
    return real_windows


def get_window_ids_of_application(application_name=None, process_id=None, filter_out_icons_and_masks=True):
    """
    Returns the ids of a particular application's windows

    :param application_name: <str> "" the application name to find
    :param process_id: The id of the process
    :param filter_out_icons_and_masks: <bool> Whether to ignore any windows which are blatantly icons or mask areas (threshold is 200px x 200px
    :return: [<id>, <id>]  List of window ids
    """
    window_ids_string_list = []
    if process_id:
        p_xdotool = Popen(["xdotool", 'search', '--pid', str(process_id)], stdout=PIPE)
        str_window_ids, err = p_xdotool.communicate()
        window_ids_string_list.append(str_window_ids)
    elif application_name:
        # We search our processlist first
        current_user = str(getpass.getuser())
        p_get_pid = Popen(["pgrep", "-u", current_user, "-i", str(application_name)], stdout=PIPE)
        pids, err = p_get_pid.communicate()
        pids = str(pids).strip().split("\n")
        pids = filter(bool, pids)
        if pids:
            print("Pids for {}: {}".format(application_name, pids))
            for pid in pids:
                if not str(pid).strip():
                    continue
                p_xdotool = Popen(["xdotool", 'search', '--pid', str(pid).strip()], stdout=PIPE)
                str_window_ids, err = p_xdotool.communicate()
                window_ids_string_list.append(str_window_ids)
        else:  # Fallback to searching via xdotool
            p_xdotool = Popen(["xdotool", 'search', '--name', application_name], stdout=PIPE)
            str_window_ids, err = p_xdotool.communicate()
            window_ids_string_list.append(str_window_ids)
    else:
        raise WindowPositionException("ERROR: get_window_ids_of_application() no application name nor pid supplied. Please provide at least one.")

    # Now suck all the data out of those processes:
    print("window_ids_string_list: {}".format(window_ids_string_list))
    actual_window_ids = []
    if window_ids_string_list:
        window_ids_string = "\n".join(window_ids_string_list)
        list_of_window_ids = window_ids_string.split("\n")
        list_of_window_ids = sorted(filter(bool, list_of_window_ids))  # Ensures the same id stays in the same place on the list
        actual_window_ids.extend(list_of_window_ids)
    if err:
        print("ERROR: {}".format(err))
    if filter_out_icons_and_masks and actual_window_ids:  # Remove any windows less than 201 x 201
        actual_window_ids = filter_to_large_enough_windows(window_ids=actual_window_ids)
        # Second pass: try the children of those windows if still empty
    if not actual_window_ids:
        return []
    return actual_window_ids


def get_window_ids_of_interest(application_name=ACTIVE_WINDOW, exclude_ids=None):
    """
    Return the window ids of the windows of interest
    :param application_name: the application name. If omitted, will use the active window
    :param exclude_ids: Iterable or comma delimited string of window IDs to ignore.
    :return: [<id>] list of window ids
    """
    if application_name == ACTIVE_WINDOW:
        window_ids = [get_window_id_of_active_window()]
    else:
        window_ids = get_window_ids_of_application(application_name=application_name, filter_out_icons_and_masks=True)
    if exclude_ids:
        if not isinstance(exclude_ids, (list, tuple, set)):
            exclude_ids = str(exclude_ids).split(",")  # Assume comma delimited
        out_window_ids = []
        exclude_str_set = set([str(exclude_id).strip() for exclude_id in exclude_ids])
        for window_id in window_ids:
            if str(window_id).strip() not in exclude_str_set:
                out_window_ids.append(cast_safe(window_id, int))
        window_ids = out_window_ids
    return window_ids


def get_first_window_id_of_interest(application_name=ACTIVE_WINDOW, exclude_ids=None):
    """
    Return the FIRST window id of the windows of interest
    :param application_name: the application name. If omitted, will use the active window
    :param exclude_ids: Iterable of window IDs to ignore. Useful if we want to get the nth window
    :return: <id> id of window of interest, or None
    """
    window_ids = get_window_ids_of_interest(application_name=application_name, exclude_ids=exclude_ids)
    try:
        return window_ids[0]
    except IndexError:
        return None


def get_detailed_properties_of_window(window_id):
    """
    Get the detailed information about a window
    :param window_id:
    :return: {
        "id": 42136835,
        "title": "Syncthing"
        "x": 1456
        "y": 454
        "w":  650
        "h":  450
        "centre_x": 1781,
        "centre_y": 679
    }
    """
    window_id = str(int(window_id))
    p_xwininfo = Popen(["xwininfo", "-id", window_id], stdout=PIPE)
    window_text, err = p_xwininfo.communicate()
    print(window_text)
    if err:
        print(err)

    window_info = {
        'x': 0,
        'y': 0,
    }

    # Extract useful information from current window:
    win_details = re_win_name.findall(window_text)
    print(win_details)
    try:
        win_details = win_details[0]
    except IndexError:
        print("ERROR: No active window found by id {id} in [get_detailed_properties_of_window({id})]".format(id=window_id))
        return {}
    else:
        window_info["id"] = win_details[0]
        window_info["title"] = win_details[1]
    win_x = re_win_x.findall(window_text)
    window_info['x'] = int(win_x[0])
    win_y = re_win_y.findall(window_text)
    window_info['y'] = int(win_y[0])
    win_w = re_win_w.findall(window_text)
    window_info['w'] = int(win_w[0])
    win_h = re_win_h.findall(window_text)
    window_info['h'] = int(win_h[0])
    midpoint_x = int(math.ceil(window_info['x'] + window_info['w']/2))
    window_info["centre_x"] = midpoint_x
    midpoint_y = int(math.ceil(window_info['y'] + window_info['h']/2))
    window_info["centre_y"] = midpoint_y
    return window_info


def get_monitor_a_location_is_on(x, y):
    """
    Return the monitor which displays stuff at the given pixel location
    :param x:
    :param y:
    :return: {
        'name': 'DP-4',
        'h': 1440,
        'w': 2560,
        'x': 1291,
        'y': 0}
    }
    """
    desktop_split_by_screens = get_screens_and_positions()

    resident_monitor = desktop_split_by_screens[0]  # Default to being positioned in first monitor
    for monitor in desktop_split_by_screens:
        if x >= monitor["x"] and x <= (monitor["x"] + monitor["w"]) and y >= monitor["y"] and y <= (monitor["y"] + monitor["h"]):
            # Window is IN!
            resident_monitor = monitor
            break
    return resident_monitor


def get_monitor_by_name_or_id(name=None, monitor_id=None):
    """
    Return the monitor given by the name or the numeric ID
    :return: {
        'name': 'DP-4',
        'h': 1440,
        'w': 2560,
        'x': 1291,
        'y': 0}
    }
    """
    if name is not None and monitor_id is not None:
        print("WARNING: get_monitor_by_name_or_id() both a monitor name and an ID were supplied. Ignoring name ({}) and using id instead (#{}).".format(name, id))
    elif name is None and monitor_id is None:
        print("WARNING: get_monitor_by_name_or_id() no monitor name or ID were supplied. Defaulting to first screen.")
    if name:
        name = str(name).strip()
    if monitor_id:
        monitor_id = int(monitor_id)

    desktop_split_by_screens = get_screens_and_positions()

    resident_monitor = desktop_split_by_screens[0]  # Default to being positioned in first monitor

    if monitor_id:
        try:
            return desktop_split_by_screens[monitor_id]
        except IndexError:
            print("ERROR: Cannot find monitor by id #{}".format(monitor_id))
            return None
    if name:
        clean_target_monitor_name = name.lower()
        for monitor in desktop_split_by_screens:
            candidate_monitor_name = str(monitor["name"]).lower().strip()
            if clean_target_monitor_name == candidate_monitor_name:
                # Window is IN!
                resident_monitor = monitor
                break
    return resident_monitor


def _spawn_missing_application(application_name, *additional_args, **additional_kwargs):
    """
    Spawns the desired application. Returns its pid and window id
    :param application_name:
    :return: (pid, window_id)
    """
    try:
        try:
            base_command = launcher_commmands[application_name.lower()]
        except KeyError:
            base_command = launcher_commmands[application_name]
    except KeyError:
        raise Exception("ERROR: Application by name '{}' does not have a launcher command. Cannot launch an instance.".format(application_name))

    safer_command = base_command.split()  # split by space

    if additional_args:
        clean_args = []
        for arg in additional_args:
            clean_arg = str(arg).strip()
            clean_args.append(clean_arg)
        clean_args_str = " ".join(clean_args)  # Collapses any dodgy nesting (args with spaces in)
        for cleaner_arg in clean_args_str.split():
            cleaner_arg = str(cleaner_arg).strip()
            safer_command.append(cleaner_arg)

    if additional_kwargs:
        for k, v in additional_kwargs.items():
            if not k.startswith("-"):
                k = "--{}".format(k).strip()
                built_kwarg = "{}={}".format(k, v.strip())
                safer_command.append(built_kwarg)

    python_version = sys.version_info
    if python_version >= (3, 8):
        import detach
        spawned_process = detach.call(safer_command)  # Python 3.8+
    elif python_version >= (3, 2):
        spawned_process = subprocess.Popen(safer_command, start_new_session=True)  # Python 2.2-3.8
    else:
        spawned_process = subprocess.Popen(safer_command)  # Python 2.2-3.8

    # Wait until we have a window
    found_window_id = None
    spawned_process_id = None
    for tries in range(0, 20):
        spawned_process_id = spawned_process.pid
        windows_from_process = get_window_ids_of_application(process_id=spawned_process_id, filter_out_icons_and_masks=True)
        if windows_from_process:
            found_window_id = windows_from_process[-1]
            break
        sleep(0.05)

    if found_window_id is None:
        found_window_id = get_first_window_id_of_interest(application_name=application_name)
    print("proc:{}, wind={}".format(spawned_process_id, found_window_id))

    return spawned_process.pid, found_window_id


def _resize_and_move_window_to_position(window_id, x, y, w, h):
    """
    Resizes the window and moves it to the desired position
    :param window_id: <int> window_id
    :param x: position of top left x
    :param y: position of top left y
    :param w: window width
    :param h: window height
    :return:
    """
    window_id = int(window_id)
    # Remove any locks on window position
    window_manipulation_command = "wmctrl -i -r {window_id} -b remove,maximized_vert,maximized_horz -v".format(window_id=str(window_id))
    exit_code_1 = subprocess.check_call(window_manipulation_command.split())
    # Resize window
    window_manipulation_command2 = "wmctrl -i -r {window_id} -e 0,{x},{y},{w},{h} -v".format(
        window_id=str(window_id),
        x=str(x),
        y=str(y),
        w=str(w),
        h=str(h)
    )
    exit_code_2 = subprocess.check_call(window_manipulation_command2.split())
    # Maximise window
    window_manipulation_command3 = "xdotool windowactivate {window_id}".format(window_id=str(window_id))
    exit_code_3 = subprocess.check_call(window_manipulation_command3.split())
    print("New window position for #%s: %sx%s %s,%s" % (str(window_id), str(w), str(h), str(x), str(y)))
    return exit_code_1 + exit_code_2 + exit_code_3


def _move_window_to_desktop(window_id, desktop_id=None):
    """
    Moves the window to the desired desktop
    :param window_id: <int> window_id
    :param desktop_id: <int> The desktop id
    :return:
    """
    if desktop_id is None:
        return 0
    exit_code = os.system(
        "wmctrl -i -r {window_id} -t {desktop_id}".format(
            window_id=str(int(window_id)),
            desktop_id=str(int(desktop_id))
        )
    )
    return exit_code


def reposition_window(application_name=None, nth_instance_of_application=0, window_id=None, target_monitor_name=None, target_position=None, target_desktop_id=None, spawn_missing=False):
    """
    Repositions the window in the desired location

    :param application_name: <str> The application name you wish to move,
    :param window_id: <int> The window id you wish to move. Use instead of application_name if you know the window you want to move
    :param nth_instance_of_application: <int> if providing an application name, you can specify which instance of this application you wish to move i.e. 3 = 4th window of it
    :param target_monitor_name: <int> The monitor you wish to move the window to. If omitted, will keep the same monitor as the window already is in.
    :param target_position: The desired position as a tuple e.g. ("top", "left")
    :param target_desktop_id: <int> The desired desktop to move a window to. If omitted, keeps it on the same desktop.
    :param spawn_missing: <bool> If True, will run a command to spawn any missing application window when using a named application so that you can then move the window.
    :return: exit code
    """

    # Determine which window we are interested in:
    if not application_name and not window_id:
        application_name = ACTIVE_WINDOW
    elif application_name and window_id:
        print("WARNING: you supplied BOTH a window ID and an application name. The application name will be ignored.")

    if window_id is not None:
        window_id = int(window_id)

    # Determine the window id we are interested in
    if application_name and not window_id:
        window_ids = get_window_ids_of_interest(application_name=application_name)
        if application_name == ACTIVE_WINDOW:
            print("ERROR: No active window.")
            return 1
        nth_instance_of_application = int(nth_instance_of_application or 0)
        try:
            window_id = window_ids[nth_instance_of_application]
        except (IndexError, KeyError):
            # Spawn it if desired - requires a relevant entry in launcher_commands:
            if spawn_missing not in (None, False, 0, "0", "", "no", "No", "NO", "x", "n"):
                try:
                    _pid, window_id = _spawn_missing_application(application_name)
                except WindowPositionException as e:
                    print(e)
                    return 1
            else:
                print("ERROR: No windows loaded for applications by name '{}'".format(application_name))
                return 1

    # Determine which position our active window is in:
    window_of_interest = get_detailed_properties_of_window(window_id)
    if not window_of_interest:
        print("ERROR: No window by id #{}".format(window_id))
        return 1
    midpoint_x = window_of_interest["centre_x"]
    midpoint_y = window_of_interest["centre_y"]

    # Determine which monitor our window mostly resides in:
    if target_monitor_name:  # If you've specified a target monitor name, go fetch that
        target_monitor = get_monitor_by_name_or_id(name=target_monitor_name)
    else:
        target_monitor = get_monitor_a_location_is_on(x=midpoint_x, y=midpoint_y)

    # Resolve desired position
    if not target_position and not target_desktop_id:
        print("ERROR: No target position defined for window ({}). Please provide one or two of: 'top'/'bottom' 'left'/'right'.".format(window_of_interest["title"] or window_id))
        print("ERROR: No desktop_id provided for window ({}).".format(window_of_interest["title"] or window_id))
        return 1

    if target_position:
        if not isinstance(target_position, (list, tuple, set)):
            target_position = tuple([target_position])

        # Now look at the arguments to see where we wish to position this window!
        lower_win_title = window_of_interest['title'].lower()
        target_monitor_margins = SCREEN_MARGINS.get(str(target_monitor["name"]), (0, 0, 0, 0)) #Default to no margins if cannot find the screen

        if "google chrome" in lower_win_title or "chromium" in lower_win_title:
            # Apply a special correction for chrome only on certain screens:
            if ("left" in target_position or "right" in target_position) and not ("top" in target_position or "bottom" in target_position):
                target_monitor_margins = CHROMIUM_MARGINS.get(str(target_monitor["name"]), (32, 0, 0, 0)) #Default to no margins if cannot find the screen

        # WIDTH + HEIGHT: Set default target width and height
        target_width = (target_monitor["w"]/1 - target_monitor_margins[1] - target_monitor_margins[3])
        target_height = (target_monitor["h"]/1 - target_monitor_margins[0] - target_monitor_margins[2])

        #If a horizontal keyword appears in the arguments, the target width is halved:
        if "left" in target_position or "right" in target_position:
            target_width = (target_monitor["w"]/2 - target_monitor_margins[1] - target_monitor_margins[3])
        #If a vertical keyword appears in the arguments, the target height is
        if "top" in target_position or "bottom" in target_position:
            target_height = (target_monitor["h"]/2 - target_monitor_margins[0] - target_monitor_margins[2])

        # POSITION - Default to top left
        target_xoff = (target_monitor['x'] + target_monitor_margins[3])
        target_yoff = (target_monitor['y'] + target_monitor_margins[0])

        if str("right") in target_position: #If 'right' appears in the arguments, offset to right of monitor:
            target_xoff = target_monitor['x'] + target_monitor['w'] - target_width - target_monitor_margins[1]
        if str("left") in target_position: #If 'left' appears in the arguments, offset to left of monitor:
            target_xoff = target_monitor['x'] + target_monitor_margins[3]
        if str("bottom") in target_position: #If 'bottom' appears in the arguments, offset to bottom of monitor:
            target_yoff = target_monitor['y'] + target_monitor['h'] - target_height - target_monitor_margins[2]
        if str("top") in target_position: #If 'left' appears in the arguments, offset to left of monitor:
            target_yoff = target_monitor['y'] + target_monitor_margins[0]

        _resize_and_move_window_to_position(window_id, target_xoff, target_yoff, target_width, target_height)

    # Move it to another desktop if desired
    if target_desktop_id is not None:
        _move_window_to_desktop(window_id, desktop_id=target_desktop_id)

    return 0


def reposition_window_and_spawn_missing(application_name=None, nth_instance_of_application=0, target_monitor_name=None, target_position=None, target_desktop_id=None):
    """
    Repositions the specified application window in the desired location, on the desired desktop.
    If the application is not running, it will run it then move the window accordingly.

    :param application_name: <str> The application name you wish to move,
    :param nth_instance_of_application: <int> if providing an application name, you can specify which instance of this application you wish to move i.e. 3 = 4th window of it
    :param target_monitor_name: <int> The monitor you wish to move the window to. If omitted, will keep the same monitor as the window already is in.
    :param target_position: The desired position as a tuple e.g. ("top", "left")
    :param target_desktop_id: <int> The desired desktop to move a window to. If omitted, keeps it on the same desktop.
    :return: exit code
    """
    return reposition_window_and_spawn_missing(
        application_name=application_name,
        nth_instance_of_application=nth_instance_of_application,
        target_monitor_name=target_monitor_name,
        target_position=target_position,
        target_desktop_id=target_desktop_id
    )


def run_layout(layout, override_kwargs=()):
    """
    Run the specified layout
    :param layout: The layout to execute!
    :param override_kwargs:
    :return:
    """
    try:
        layout_list = layouts[str(layout).strip()]
    except KeyError:
        try:
            layout_list = layouts[str(layout).lower().strip()]
        except KeyError:
            raise WindowPositionException("No such layout by name '{}'".format(layout))

    # Now work out override. Bin any default values:
    final_override_kwargs = {}
    for k, v in override_kwargs.items():
        if v not in (None, False, "", [], ()):  # We DO allow zeros
            final_override_kwargs[k] = v

    # Build our finals
    strategy_kwargs = {}
    strategy_kwargs.update(final_override_kwargs)  # Now we get our lovely overrides in there

    # Now parse that layout!
    successes = []
    failures = []
    for layout_strategy in layout_list:
        this_strategy_kwargs = copy.deepcopy(layout_strategy)  # Take the dict from the layout strategy without polluting it
        this_strategy_kwargs.update(final_override_kwargs)
        print("{} ---> \n{}".format(layout_strategy, this_strategy_kwargs))
        error_code = reposition_window(**this_strategy_kwargs)
        if error_code:
            failures.append(layout_strategy)
        else:
            successes.append(layout_strategy)

    print("Successes: {}".format(successes))
    print("Failures: {}".format(failures))
    return len(failures)


# Run when directly called
if __name__ == "__main__":
    usage = [
        "Windowpos: Sane way to move your windows around from the command line.",
        "",
        "  Moving currently active window, specify top/bottom and/or left/right or middle:",
        "\tpython ./{} top".format(__file__),
        "\tpython ./{} top left".format(__file__),
        "\tpython ./{} top right".format(__file__),
        "\tpython ./{} bottom".format(__file__),
        "\tpython ./{} bottom left".format(__file__),
        "\tpython ./{} bottom right".format(__file__),
        "\tpython ./{} left".format(__file__),
        "\tpython ./{} right".format(__file__),
        "\tpython ./{} middle".format(__file__),
        "",
        "  Moving specific application's first window, specify -n or --name:",
        "\tpython ./{} -n=brave top left".format(__file__),
        "\tpython ./{} --name=brave top left".format(__file__),
        "",
        "  Moving specific application's additional window, specify -n or --name and -i or --instance.",
        "\tpython ./{} -n=brave -i=2 top left".format(__file__),
        "\tpython ./{} --name=brave --instance=2 top left".format(__file__),
        ""
        "  Moving currently active window to a different monitor, specify -m or --monitor. If omitted will use the monitor the window is currently on.",
        "\tpython ./{} -m=DP-2 top".format(__file__),
        "\tpython ./{} --monitor=DP-2 top left".format(__file__),
        "",
        "  Moving currently active window to a different desktop, specify -d or --desktop. If omitted will use the desktop the window is currently on.",
        "\tpython ./{} -d=1 top".format(__file__),
        "\tpython ./{} --desktop=1 top left".format(__file__),
        "",
        "",
        "Options:",
        "\t-n, --name        the name of the application. If omitted, defaults to currently selected window.",
        "\t-i, --instance    the instance of the application where there is more than one. Must also use -n or --name",
        "\t-m, --monitor     which monitor to move the window to",
        "\t-d, --desktop     which desktop to move the window to (when using multiple desktops)",
        "\t-s, --layout      run the specified layout. Other options supplied will override the layout strategy.",
        ""
    ]
    ap = argparse.ArgumentParser(usage="\n".join(usage))
    ap.add_argument("-n", "--name", dest="application_name", default=None, required=False, help="The application name you wish to move the window of.")
    ap.add_argument("-i", "--instance", dest="nth_instance_of_application", default=None, required=False, help="Where an application has more than one window, which of the windows you wish to move.")
    ap.add_argument("-m", "--monitor", dest="target_monitor_name", default="", required=False, help="Which monitor screen you want to put the window on.")
    ap.add_argument("-d", "--desktop", dest="target_desktop_id", required=False, help="Which desktop (when using multiple desktops) you wish to put the window on.")
    ap.add_argument("-s", "--spawn", dest="spawn_missing", default=False, required=False, help="Should absent windows be spawned?")
    ap.add_argument("-l", "--layout", dest="layout", default="", required=False, help="Which preconfigured layout you wish to achieve.")
    ap.add_argument(dest="target_position", nargs=argparse.REMAINDER)
    args = vars(ap.parse_args())
    layout_name = args.pop("layout")
    if not layout_name:
        reposition_window(**args)
    else:
        run_layout(layout=layout_name, override_kwargs=args)
