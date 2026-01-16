#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# :copyright: (c) 2019-2020 Guilhem Charles. All rights reserved.
"""Generate visualization of a ninja build from its logs."""
import argparse
import math
import re
import sys
from os.path import basename, getmtime
from typing import List, Optional

TIMELINE = """
<!DOCTYPE HTML>
<html>
<head>
  <title>{title}</title>

  <style type="text/css">
    body, html {{
      font-family: sans-serif;
    }}
  </style>

  <script src="https://unpkg.com/vis-timeline@8.5.0/standalone/umd/vis-timeline-graph2d.min.js"></script>
</head>
<body>
<div id="visualization"></div>

<script type="text/javascript">
  // DOM element where the Timeline will be attached
  var container = document.getElementById('visualization');

  // Create a DataSet (allows two way data-binding)
  var items = new vis.DataSet({dataset});
  // Configuration for the Timeline
  var options = {{
    "margin": {{
      "item": {{
        "horizontal": 0,
        "vertical": 2
      }}
    }},
    "max": {maxTime},
    "min": {minTime}
  }};

  // Create a Timeline
  var timeline = new vis.Timeline(container, items, options);
</script>
</body>
</html>
"""


def generate_build_profile(logfile: str) -> List[dict]:
    """
    Parse a ninja build log file and generates a profile. A profile consist of the list of item
    part of the build.

    :param logfile: Path to the build log file.
    :return: Profile of the build.
    """

    def parse_build_entry(line: str) -> Optional[dict]:
        try:
            # ignore comments
            if line[:1] != "#":
                start_offset, end_offset, timestamp, output, command_hash = line.split()
                return {
                    "start_offset": int(start_offset),
                    "end_offset": int(end_offset),
                    "timestamp": int(timestamp),
                    "output": output,
                    "command_hash": command_hash
                }
        except ValueError:
            print(f"error: could not parse {line}", file=sys.stderr)
        return None

    profile = []
    with open(logfile, "r") as build_log:
        # first line might be a header specifying ninja build log version
        header = build_log.readline()
        log_version = re.search(r"# ninja log v(\d+)", header)
        if log_version:
            parsed_version = log_version.group(1)
            if int(parsed_version) < 5 or int(parsed_version) > 7:
                raise RuntimeError(f"unsupported log file version: {parsed_version}")
        else:
            # header is a log entry
            parsed_project = parse_build_entry(header)
            if parsed_project:
                profile = [parsed_project]
        # handle remaining lines, filter out entries that could not be parsed
        profile.extend(filter(None, (parse_build_entry(line) for line in build_log)))
        outputs = set()
        dedupedProfile = list()
        maxTimestamp = -math.inf
        maxStartOffset = -math.inf
        for entry in reversed(profile):
            if not entry["output"] in outputs:
                outputs.add(entry["output"])
                dedupedProfile.append(entry)
                maxTimestamp = max(entry["timestamp"], maxTimestamp)
                maxStartOffset = max(entry["start_offset"], maxStartOffset)

        if int(parsed_version) >= 6:
            # start of 2012, the initial release of Ninja, in nanoseconds since Unix epoch
            if maxTimestamp < 1325376000 * 1000000000:
                # wacky Windows format based on Windows FILETIME with Ninja-specific epoch offset
                maxTimestamp += 12622770400 * 10000000
                # now we're a Windows FILETIME - 1 per 100ns since 1600
                maxTimestamp = (maxTimestamp - 116444736000000000) // 10000
            else:
                # nanos since Unix epoch
                maxTimestamp = maxTimestamp // 1000000
        else:
            # start of 2012, the initial release of Ninja, in seconds since Unix epoch
            if maxTimestamp < 1325376000:
                # different Ninja-specific wacky Windows format
                # for this, they had an excuse, as it makes it fit in 32-bits
                maxTimestamp += 12622770400
                maxTimestamp *= 10000000
                # now we're a Windows FILETIME - 1 per 100ns since 1600
                maxTimestamp = (maxTimestamp - 116444736000000000) // 10000
            else:
                maxTimestamp *= 1000
        startTimestamp = maxTimestamp - maxStartOffset

        for entry in dedupedProfile:
            entry["start"] = entry["start_offset"] + startTimestamp
            entry["end"] = entry["end_offset"] + startTimestamp

        return dedupedProfile
    return []

def generate_timeline_from(profile: List[dict], output: str, title: str):
    """
    Generate a visjs timeline from the ninja build profile.

    :param profile: Ninja build information.
    :param output: File to output the visualization.
    :param title: Title of the visualization.
    :return:
    """

    def profile_entry_to_timeline_entry(entry: dict):
        return {
            "content": basename(entry["output"]),
            "start": entry["start"],
            "end": entry["end"],
            "title": f"{entry["end"] - entry["start"]}ms {entry["output"]}",
        }

    try:
        minTime = math.inf
        maxTime = -math.inf
        dataset = list()
        for node in profile:
            minTime = min(minTime, node["start"])
            maxTime = max(maxTime, node["end"])
            dataset.append(profile_entry_to_timeline_entry(node))
        minTime -= 1000
        maxTime += 1000
        with open(output, "w") as visualization:
            visualization.write(TIMELINE.format(title=title, dataset=dataset, minTime=minTime, maxTime=maxTime))
    except RuntimeError as exc:
        print(f"error: could not generate timeline: {exc}", file=sys.stderr)
        sys.exit(1)


def get_argparser() -> argparse.ArgumentParser:
    """
    ninjavis arguments parser.

    :return: Arguments parser.
    """
    parser = argparse.ArgumentParser(
        prog="ninjavis",
        description="Parse ninja build log file and " "generates a timeline of the build",
    )
    parser.add_argument("logfile", help="Ninja build log (.ninja_log)")
    parser.add_argument("output", help="Output file for the visualization")
    parser.add_argument("--title", help="Visualization title", default="Ninja build")
    return parser


def main():
    """
    Parse the arguments and try to generate a visualization out of the provided build log.

    :return:
    """
    args = get_argparser().parse_args(sys.argv[1:])

    try:
        profile = generate_build_profile(args.logfile)
        generate_timeline_from(profile, args.output, args.title)
    except (RuntimeError, FileNotFoundError) as err:
        print(err, file=sys.stderr)
        sys.exit(1)
    sys.exit(0)

if __name__ == '__main__':
    main()
