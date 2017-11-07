#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import subprocess
import argparse
import time
from datetime import datetime as dt

def closest(num, arr):
	filtered = filter(lambda x: x >= num, arr)
	return min(filtered)

def parse_ffmpeg_timestamp(timestamp, debug):
	timestamp_formats = ["%H:%M:%S.%f", "%H:%M:%S", "%M:%S.%f", "%M:%S"]

	try:
		parsed = float(timestamp)
		return parsed
	except ValueError:
		zero = dt(1900,1,1)
		for fmt in timestamp_formats:
			try:
				parsed = dt.strptime(timestamp, fmt)
				if debug:
					print(f"Parsed timestamp {timestamp} with {fmt}")
			except ValueError:
				continue

		return round((parsed - zero).total_seconds(), 4)
	else:
		return 0

def get_video_info(video):
	ffprobe_args = ["ffprobe", "-i", video,
							"-select_streams", "v:0",
							"-loglevel", "quiet",
							"-show_entries", "stream=width,height,duration,r_frame_rate"]

	p = subprocess.Popen(ffprobe_args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)

	p.stdout.readline() # skip "[STREAM]"

	ffprobe_results = [p.stdout.readline().strip() for i in range(4)]
	ffprobe_returnobj = {}

	for item in ffprobe_results:
		parts = item.split("=")
		if "/" in parts[1]:
			partparts = parts[1].split("/")
			ffprobe_returnobj[parts[0]] = round(float(partparts[0]) / float(partparts[1]), 2)
		else:
			ffprobe_returnobj[parts[0]] = float(parts[1])

	return ffprobe_returnobj

def main():
	start = time.time()

	parser = argparse.ArgumentParser(description="Automate ffmpeg stuff")
	parser.add_argument("-i", metavar="input", type=str, required=True, help="Input file")
	parser.add_argument("-ss", metavar="start time", type=str, default="0", help="Start time")

	duration_group = parser.add_mutually_exclusive_group()
	duration_group.add_argument("-t", metavar="duration", type=str, default=None, help="Duration")
	duration_group.add_argument("-to", metavar="position", type=str, default=None, help="Position")

	parser.add_argument("-vt", "--title", metavar="video title", type=str, default=None, help="Video title")
	parser.add_argument("-m", "--mute", action="store_true", help="Mute audio")
	parser.add_argument("-f", "--fade", metavar="fade duration", type=str, default=None, help="Fade in/out duration in seconds. Takes priority over -fi and -fo")
	parser.add_argument("-fi", "--fadein", metavar="fade in duration", type=str, default=None, help="Fade in duration in seconds")
	parser.add_argument("-fo", "--fadeout", metavar="fade out duration", type=str, default=None, help="Fade out duration in seconds")
	parser.add_argument("-vh", "--height", metavar="video height", type=str, default=None, help="New video height (keeps aspect ratio)")
	parser.add_argument("-c", "--codec", type=str, choices=["libx264", "libx265"], default="libx264", help="Codec choice")
	parser.add_argument("--fixrgb", type=str, default=None, help="Convert TV RGB range to PC RGB range (hacky)")
	parser.add_argument("--debug", action="store_true", help="Debug mode (displays lots of additional information)")

	extra_group = parser.add_mutually_exclusive_group()
	extra_group.add_argument("-yt", "--youtube", action="store_true", help="YouTube mode (adds options to make YouTube happy)")
	extra_group.add_argument("-hw", "--hardware", action="store_true", help="Enable hardware acceleration (Only Nvidia, experimental)")

	parser.add_argument("out", type=str, help="out file")

	args = parser.parse_args()

	CRF_X264 = 20
	CRF_X265 = 24
	CQ_NVENC = 0
	QP_NVENC = 21
	PRESET = "slow"

	YT_BITRATES = {
		30: {
			2880: "64M",
			2160: "45M",
			1440: "16M",
			1080: "8M",
			720: "5M",
			480: "3M",
			360: "1M"
		},
		60: {
			2880: "80M",
			2160: "64M",
			1440: "24M",
			1080: "12M",
			720: "8M",
			480: "4M",
			360: "2M"
		}
	}

	if args.fade:
		args.fadein = args.fade
		args.fadeout = args.fade

	if args.hardware:
		args.codec = "h264_nvenc"

	video_info = get_video_info(args.i)

	start_secs = parse_ffmpeg_timestamp(args.ss, args.debug)
	if args.to:
		duration_secs = parse_ffmpeg_timestamp(args.to, args.debug) - start_secs
	if args.t:
		duration_secs = parse_ffmpeg_timestamp(args.t, args.debug)
	else:
		duration_secs = video_info["duration"] - start_secs

	fadeout_start = round(start_secs + duration_secs - float(args.fadeout or 0), 4)

	if args.height:
		if args.hardware:
			filter_scale = f"scale_cuda=-1:{int(args.height)}"
		else:
			filter_scale = f"scale=-1:{int(args.height)}:flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp"
	else:
		filter_scale = None

	# Just set all the important parameters and hope that's enough (if fixrgb > 0)
	opt_fixrgb = ["-colorspace", "bt709", "-color_range", "jpeg", "-color_primaries", "bt709", "-color_trc", "bt709"] if (args.fixrgb or 0) > 0 else []

	# Force the video output to full range RGB as well (if fixrgb == 2)
	filter_fixrgb = "scale=in_range=tv:out_range=pc" if args.fixrgb == "2" else None

	filter_vfadein = f"fade=t=in:st={start_secs}:d={args.fadein}" if args.fadein else None
	filter_vfadeout = f"fade=t=out:st={fadeout_start}:d={args.fadeout}" if args.fadeout else None

	if args.hardware:
		filter_vfadein = f"hwdownload,format=nv12,{filter_vfadein},hwupload" if args.fadein else None
		filter_vfadeout = f"hwdownload,format=nv12,{filter_vfadeout},hwupload" if args.fadeout else None

	filter_afadein = f"afade=t=in:st={start_secs}:d={args.fadein}:curve=ihsin" if args.fadein else None
	filter_afadeout = f"afade=t=out:st={fadeout_start}:d={args.fadeout}:curve=ihsin" if args.fadeout else None

	filter_vfade = ",".join(filter(None, [filter_vfadein, filter_vfadeout]))
	filter_afade = ",".join(filter(None, [filter_afadein, filter_afadeout]))

	opt_metadata = ["-metadata", f"title=\"{args.title}\""] if args.title else []

	opt_vcodec = args.codec

	opt_acodec = ["-acodec", "copy"] if not (args.fadein or args.fadeout) else ["-acodec", "aac", "-b:a", "384k"]
	opt_audio = ["-an"] if args.mute else opt_acodec
	opt_afilter = ["-af", filter_afade] if filter_afade and not args.mute else []

	opt_duration = ["-t", str(duration_secs)] if args.t or args.to else []

	opt_vfilter_joined = ",".join(filter(None, [filter_scale, filter_fixrgb, filter_vfade]))
	opt_vfilter = ["-vf", opt_vfilter_joined] if opt_vfilter_joined else []

	yt_index1 = closest(video_info["r_frame_rate"], YT_BITRATES.keys())
	yt_index2 = closest(video_info["height"], YT_BITRATES[yt_index1].keys())
	yt_bitrate = YT_BITRATES[yt_index1][yt_index2]
	opt_youtube = ["-movflags", "faststart", 
				   "-maxrate", yt_bitrate,
				   "-bufsize", f"{round(int(yt_bitrate[:-1])*1.5)}M",
				   "-g", f"{video_info['r_frame_rate'] / 2}",
				   "-bf", "2",
				   "-pix_fmt", "yuv420p"] \
				   if args.youtube and not args.hw else []

	opt_hwaccel = "-hwaccel cuvid -c:v h264_cuvid".split(" ") if args.hardware else []

	CODEC_OPTIONS = {
		"libx264": f"-crf {CRF_X264} -preset {PRESET} -tune film -profile:v high".split(" ") + opt_fixrgb + opt_youtube,
		"libx265": f"-crf {CRF_X265}".split(" "),
		"h264_nvenc": f"-preset {PRESET} -profile:v high -level 5.1 -rc constqp -qp {QP_NVENC} -strict_gop true -rc-lookahead 32 -spatial-aq true -temporal-aq true -aq-strength 15".split(" ")
	}

	ffmpeg_args = ["ffmpeg"] + opt_hwaccel + \
					   ["-i", f"{args.i}",
						"-ss", args.ss,
						"-c:v", args.codec] + \
						opt_audio + opt_afilter + \
						CODEC_OPTIONS[args.codec] + \
						opt_vfilter + opt_metadata + opt_duration + \
						["-y", f"{args.out}"]

	if args.debug:
		print("#" * 40)

		print("ffprobe output:", video_info)
		print("Start time in seconds:", start_secs)
		print("Duration in seconds:", duration_secs)
		print("Video fade filter:", filter_vfade)
		print("Audio fade filter:", filter_afade)

		if args.youtube and not args.hw:
			print("YouTube arguments:\n", " ".join(opt_youtube))

		print("ffmpeg arguments:\n", " ".join(ffmpeg_args))

		print("#" * 40)
		input("Press Enter to continue...")
		# sys.exit(0)

	p = subprocess.Popen(ffmpeg_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

	oldline = ""
	while True:
		line = p.stdout.readline().strip()
		if line == "" and p.poll() is not None:
			returncode = p.returncode
			if returncode == 0:
				# ffmpeg has successfully exited
				end = time.time()
				print(f"ffmpeg completed in {time.strftime('%H:%M:%S', time.gmtime(end - start))}")
			else:
				print(f"ffmpeg has terminated with code {p.returncode}")
			break

		if line != oldline:
			print(line)

		oldline = line

if __name__ == '__main__':
	main()