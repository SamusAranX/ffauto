#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import subprocess
import argparse
from datetime import datetime as dt

def parse_ffmpeg_timestamp(timestamp):
	timestamp_formats = ["%H:%M:%S.%f", "%H:%M:%S", "%M:%S.%f", "%M:%S"]

	try:
		parsed = float(timestamp)
		return parsed
	except ValueError:
		zero = dt(1900,1,1)
		for fmt in timestamp_formats:
			try:
				parsed = dt.strptime(timestamp, fmt)
				print(f"Parsed timestamp {timestamp} with {fmt}")
			except ValueError:
				continue

		return (parsed - zero).total_seconds()
	else:
		return 0


def main():
	parser = argparse.ArgumentParser(description="Automate ffmpeg stuff")
	parser.add_argument("-i", metavar="input", type=str, required=True, help="Input file")
	parser.add_argument("-ss", metavar="start time", type=str, default="0", help="Start time")
	parser.add_argument("-t", metavar="duration", type=str, default=None, help="Duration")
	parser.add_argument("-vt", "--title", metavar="video title", type=str, default=None, help="Video title")
	parser.add_argument("-m", "--mute", action="store_true", help="Mute audio")
	parser.add_argument("-f", "--fade", metavar="fade in/out duration", type=str, default=None, help="Fade in/out duration in seconds. Takes priority over -fi and -fo")
	parser.add_argument("-fi", "--fadein", metavar="fade in duration", type=str, default=None, help="Fade in duration in seconds")
	parser.add_argument("-fo", "--fadeout", metavar="fade out duration", type=str, default=None, help="Fade out duration in seconds")
	parser.add_argument("-vh", "--height", metavar="video height", type=str, default=None, help="New video height (keeps aspect ratio)")
	parser.add_argument("-r", metavar="framerate", type=str, default=None, help="New frame rate")
	parser.add_argument("-c", "--codec", type=str, choices=["libx264", "libx265"], default="libx264", help="Codec choice")
	parser.add_argument("--fixrgb", type=str, default=None, help="Convert TV RGB range to PC RGB range")
	parser.add_argument("--debug", action="store_true", help="Debug mode (makes stuff go faster)")
	parser.add_argument("out", type=str, help="out file")

	args = parser.parse_args()

	CRF_X264 = 20
	CRF_X265 = 24
	PRESET = "slower" if not args.debug else "ultrafast"

	codec_options = {
		"libx264": ["-crf", str(CRF_X264)],
		"libx265": ["-crf", str(CRF_X265)]
	}

	if args.fade:
		args.fadein = args.fade
		args.fadeout = args.fade

	start_secs = parse_ffmpeg_timestamp(args.ss)
	duration_secs = parse_ffmpeg_timestamp(args.t) if args.t else 0

	filter_scale = f"scale=-1:{int(args.height)}:flags=lanczos" if args.height else None

	filter_fixrgb = None
	opt_fixrgb = []
	if args.fixrgb == "1":
		filter_fixrgb = "scale=in_range=tv:out_range=pc"
		opt_fixrgb = ["-colorspace", "bt709", "-color_range", "jpeg", "-color_primaries", "bt709", "-color_trc", "bt709"]
	elif args.fixrgb == "2":
		opt_fixrgb = ["-colorspace", "bt709", "-color_range", "jpeg", "-color_primaries", "bt709", "-color_trc", "bt709"]

	filter_vfadein = f"fade=t=in:st={start_secs}:d={args.fadein}" if args.fadein else None
	filter_vfadeout = f"fade=t=out:st={start_secs + duration_secs - float(args.fadeout)}:d={args.fadeout}" if args.fadeout else None

	filter_afadein = f"afade=t=in:st={start_secs}:d={args.fadein}:curve=ihsin" if args.fadein else None
	filter_afadeout = f"afade=t=out:st={start_secs + duration_secs - float(args.fadeout)}:d={args.fadeout}:curve=ihsin" if args.fadeout else None

	filter_vfade = ",".join(filter(None, [filter_vfadein, filter_vfadeout]))
	filter_afade = ",".join(filter(None, [filter_afadein, filter_afadeout]))

	opt_metadata = ["-metadata", f"title=\"{args.title}\""] if args.title else []

	opt_acodec = ["-acodec", "copy"] if not (args.fadein or args.fadeout) else ["-acodec", "aac", "-b:a", "192k"]
	opt_audio = ["-an"] if args.mute else opt_acodec
	opt_afilter = ["-af", filter_afade] if filter_afade and not args.mute else []

	opt_framerate = ["-r", args.r] if args.r else []
	opt_duration = ["-t", args.t] if args.t else []

	opt_vfilter_joined = ",".join(filter(None, [filter_scale, filter_fixrgb, filter_vfade]))
	opt_vfilter = ["-vf", opt_vfilter_joined] if opt_vfilter_joined else []

	if args.debug:
		print("#" * 40)

		print("Start time in seconds:", start_secs)
		print("Duration in seconds:", duration_secs)
		print("Video fade filter:", filter_vfade)
		print("Audio fade filter:", filter_afade)

		print("#" * 40)

	ffmpeg_args = ["ffmpeg", "-ss", args.ss,
							"-i", f"{args.i}",
							"-preset", PRESET,
							"-vcodec", args.codec] + \
							opt_audio + opt_framerate + \
							opt_vfilter + opt_afilter + \
							opt_fixrgb + opt_metadata + \
							codec_options[args.codec] + \
							opt_duration + \
							["-y", f"{args.out}"]

	print(" ".join(ffmpeg_args))
	# sys.exit(0)

	p = subprocess.Popen(ffmpeg_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

	oldline = ""
	while True:
		line = p.stdout.readline().strip()
		if line == "" and p.poll() is not None:
			print(f"ffmpeg has terminated: {p.returncode}")
			break

		if line != oldline:
			print(line)

		oldline = line

if __name__ == '__main__':
	main()