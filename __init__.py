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
    @date:     2016-02-26
    @version:  20160226
"""

import os
import re
import sys
from subprocess import Popen, PIPE


#How much space on each screen is consumed by always-on-top panels / margins etc. Uses CSS syntax: (top, right, bottom, left)
SCREEN_MARGINS = {
                    "DVI-1-0" : (0,0,32,0),
                    "HDMI-0" : (0,0,32,0),
                  }



#Commands for sending to shell
CMD_GET_ACTIVE_MONITORS = "xrandr | grep -w connected"

CMD_GET_ACTIVE_WINDOW = "xwininfo -id $(xdotool getactivewindow)"

CMD_MOVE_ACTIVE_WINDOW = "wmctrl -r :ACTIVE: -b remove,maximized_vert,maximized_horz && wmctrl -r :ACTIVE: -e 0,{x},{y},{w},{h}"


#Regexes
re_dims = re.compile("([0-9]+)x([0-9]+)\+([-0-9]+)\+([-0-9]+).*$")
re_win_name = re.compile('^.*Window\sid:\s([A-Fa-f0-9]+x[A-Fa-f0-9]+)\s"(.*)".*$', re.MULTILINE)
re_win_x = re.compile('^.*Absolute\supper\-left\sX:\s+([0-9]+).*$', re.MULTILINE)
re_win_y = re.compile('^.*Absolute\supper\-left\sY:\s+([0-9]+).*$', re.MULTILINE)
re_win_w = re.compile('^.*Width:\s+([0-9]+).*$', re.MULTILINE)
re_win_h = re.compile('^.*Height:\s+([0-9]+).*$', re.MULTILINE)


def window_reposition(*args, **kwargs):
    """
    Runs the program!
    """
    desktop = [] #Lists screens
    window_current = {  'x' : 0,
                        'y' : 0,
                    }
    window_target = {   'x' : 0,
                        'y' : 0,
                        'w' : 0,
                        'h' : 0
                    }
    
    #Get our desktop
    p_xrandr = Popen(["xrandr"], stdout=PIPE)
    p_mons = Popen(["grep","-w","connected"], stdin=p_xrandr.stdout, stdout=PIPE)
    monitor_text, err = p_mons.communicate()

    
    #Parse the monitors into dicts
    for monitor_line in monitor_text.split("\n"):
        print(monitor_line)
        monitor_dict = {}
        words = monitor_line.split(" ")
        monitor_dict['name'] = words[0] #First item is ALWAYS the monitor name
        dims = re_dims.findall(monitor_line)
        try:
            dims = dims[0] #Matches all sit inside a tuple, inside a list!!
        except IndexError:
            #There's no screen on this line!
            pass
        else:
            print dims
            monitor_dict["w"] = int(dims[0])
            monitor_dict["h"] = int(dims[1])
            monitor_dict["x"] = int(dims[2])
            monitor_dict["y"] = int(dims[3])
            desktop.append(monitor_dict)
    print(desktop)        
    
    
    #Determine which position our active window is in:
    p_xdotool = Popen(["xdotool",'getactivewindow'], stdout=PIPE)
    active_window, err = p_xdotool.communicate()
    p_xwininfo = Popen(["xwininfo","-id", active_window], stdout=PIPE)
    window_text, err = p_xwininfo.communicate()
    
    
    #Extract useful information from current window:
    win_details = re_win_name.findall(window_text)
    try:
        win_details = win_details[0]
    except IndexError:
        sys.exit("No active window found!")
    else:
        window_current["id"] = win_details[0]
        window_current["title"] = win_details[1]
    win_x = re_win_x.findall(window_text)
    window_current['x'] = int(win_x[0])
    win_y = re_win_y.findall(window_text)
    window_current['y'] = int(win_y[0])
    win_w = re_win_w.findall(window_text)
    window_current['w'] = int(win_w[0])
    win_h = re_win_h.findall(window_text)
    window_current['h'] = int(win_h[0])
    
    
    #Determine which monitor our window mostly resides in:
    midpoint_x = window_current['x'] + int(window_current['w']/2)
    window_current["centre_x"] = midpoint_x
    midpoint_y = window_current['y'] + int(window_current['h']/2)
    window_current["centre_y"] = midpoint_y
    #
    resident_monitor = desktop[0] #Default to being positioned in first monitor
    for monitor in desktop:
        if midpoint_x >= monitor["x"] and midpoint_x <= (monitor["x"] + monitor["w"]) and midpoint_y >= monitor["y"] and midpoint_y <= (monitor["y"] + monitor["h"]):
            #Window is IN!
            window_current["monitor"] = monitor
            resident_monitor = monitor
            break  
    print(window_current)
    
    
    #Now look at the arguments to see where we wish to position this window!
    resident_monitor_margins = SCREEN_MARGINS.get(resident_monitor["name"], (0,0,0,0)) #Default to no margins if cannot find the screen
    print resident_monitor_margins
    
    #WIDTH + HEIGHT: Set default target width and height
    target_width = (resident_monitor["w"]/1 - resident_monitor_margins[1] - resident_monitor_margins[3])
    target_height = (resident_monitor["h"]/1 - resident_monitor_margins[0] - resident_monitor_margins[2])
    
    #If a horizontal keyword appears in the arguments, the target width is halved:
    try:
        args = args[0]
    except IndexError: #No args supplied
        pass
    if str("left") in args or str("right") in args:
        target_width = (resident_monitor["w"]/2 - resident_monitor_margins[1] - resident_monitor_margins[3])
    #If a vertical keyword appears in the arguments, the target height is
    if str("top") in args or str("bottom") in args:   
        target_height = (resident_monitor["h"]/2 - resident_monitor_margins[0] - resident_monitor_margins[2])
        
    
    #POSITION - Default to top left
    target_xoff = (resident_monitor['x'] + resident_monitor_margins[3])
    target_yoff = (resident_monitor['y'] + resident_monitor_margins[0])
    
    if str("right") in args: #If 'right' appears in the arguments, offset to right of monitor:
        target_xoff = resident_monitor['x'] + resident_monitor['w'] - target_width - resident_monitor_margins[1]
    if str("left") in args: #If 'left' appears in the arguments, offset to left of monitor:
        target_xoff = resident_monitor['x'] + resident_monitor_margins[3]
    if str("bottom") in args: #If 'bottom' appears in the arguments, offset to bottom of monitor:
        target_yoff = resident_monitor['y'] + resident_monitor['h'] - target_height - resident_monitor_margins[2]
    if str("top") in args: #If 'left' appears in the arguments, offset to left of monitor:
        target_yoff = resident_monitor['y'] + resident_monitor_margins[0]
        
    print("New window position: %sx%s %s,%s" % (str(target_width), str(target_height), str(target_xoff), str(target_height)))
    
    
    #Finally, apply this new window position:
    os_apply = os.system("wmctrl -r :ACTIVE: -b remove,maximized_vert,maximized_horz && wmctrl -r :ACTIVE: -e 0,{x},{y},{w},{h}".format(x=str(target_xoff), y=str(target_yoff), w=str(target_width), h=str(target_height)))

"""
    Run when directly called
"""
if __name__ == "__main__":
    sysargs = sys.argv
    window_reposition(sysargs[1:]) #Pass in all but first arg (which is this script's name!)
    
    