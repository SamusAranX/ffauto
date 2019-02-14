#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import subprocess
import argparse
import time
import json
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
		ret_val = -1
		for fmt in timestamp_formats:
			try:
				parsed = dt.strptime(timestamp, fmt)
				ret_val = round((parsed - zero).total_seconds(), 4)
				if debug:
					print(f"Parsed timestamp {timestamp} with {fmt} and got {ret_val}")
			except ValueError:
				continue

		return ret_val
	else:
		return 0

def get_video_info(video, debug):
	ffprobe_args = ["ffprobe", "-i", video,
							"-select_streams", "v:0",
							"-hide_banner",
							"-print_format", "json",
							# "-loglevel", "quiet",
							"-show_entries", "stream=width,height,duration,r_frame_rate"]

	p = subprocess.Popen(ffprobe_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

	ffprobe_output = p.stdout.read()
	ffprobe_stderr = p.stderr.read()
	ffprobe_json = json.loads(ffprobe_output)

	if "streams" not in ffprobe_json:
		if debug:
			print(f"ffprobe args: {ffprobe_args}")
			print(f"ffprobe output: {ffprobe_output}")
			if ffprobe_stderr:
				print(ffprobe_stderr)
		raise RuntimeError("ffprobe failed.")

	stream = ffprobe_json["streams"][0]

	if "/" in stream["r_frame_rate"]:
		dividend, divisor = stream["r_frame_rate"].split("/")
		stream["r_frame_rate"] = int(dividend)/int(divisor)

	stream["duration"] = float(stream["duration"])

	return stream

def main():
	start = time.time()

	parser = argparse.ArgumentParser(description="Automate ffmpeg stuff")
	parser.add_argument("-i", metavar="input", type=str, required=True, help="Input file")
	parser.add_argument("-ss", metavar="start time", type=str, default="0", help="Start time")

	duration_group = parser.add_mutually_exclusive_group()
	duration_group.add_argument("-t", metavar="duration", type=str, default=None, help="Duration")
	duration_group.add_argument("-to", metavar="position", type=str, default=None, help="Position")

	audio_group = parser.add_mutually_exclusive_group()
	audio_group.add_argument("-m", "--mute", action="store_true", help="Mute audio")
	audio_group.add_argument("-af", "--audio-force", action="store_true", help="Force convert audio")
	audio_group.add_argument("-av", "--volume", metavar="audio volume", type=str, default=None, help="Audio volume adjustment factor")

	parser.add_argument("-vt", "--title", metavar="video title", type=str, default=None, help="Video title")
	parser.add_argument("-f", "--fade", metavar="fade duration", type=str, default=None, help="Fade in/out duration in seconds. Takes priority over -fi and -fo")
	parser.add_argument("-fi", "--fadein", metavar="fade in duration", type=str, default=None, help="Fade in duration in seconds")
	parser.add_argument("-fo", "--fadeout", metavar="fade out duration", type=str, default=None, help="Fade out duration in seconds")
	parser.add_argument("-c", "--crop", metavar="w:h:x:y", type=str, default=None, help="New video region")
	parser.add_argument("-r", "--framerate", metavar="target framerate", type=str, default=None, help="New video frame rate")
	parser.add_argument("-vh", "--height", metavar="video height", type=str, default=None, help="New video height (keeps aspect ratio)")
	parser.add_argument("-vc", "--codec", type=str, choices=["libx264", "libx265"], default="libx264", help="Codec choice")
	parser.add_argument("-ff", "--ffmpeg", type=str, default=None, help="passthrough arguments for ffmpeg")
	parser.add_argument("--fixrgb", type=str, default="0", help="Convert TV RGB range to PC RGB range (hacky)")
	parser.add_argument("--debug", action="store_true", help="Debug mode (displays lots of additional information)")

	extra_group = parser.add_mutually_exclusive_group()
	extra_group.add_argument("-yt", "--youtube", action="store_true", help="YouTube mode (adds options to make YouTube happy)")
	extra_group.add_argument("-nv", "--nvidia", action="store_true", help="Enable hardware acceleration for Nvidia GPUs (experimental)")
	extra_group.add_argument("-ap", "--apple", action="store_true", help="Enable hardware acceleration for macOS (experimental)")

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

	if args.nvidia:
		args.codec = "h264_cuvid"
	elif args.apple:
		args.codec = "h264_videotoolbox"

	video_info = get_video_info(args.i, args.debug)

	start_secs = parse_ffmpeg_timestamp(args.ss, args.debug)
	if args.to:
		duration_secs = parse_ffmpeg_timestamp(args.to, args.debug) - start_secs
	elif args.t:
		duration_secs = parse_ffmpeg_timestamp(args.t, args.debug)
	else:
		duration_secs = video_info["duration"] - start_secs

	fadeout_start = round(duration_secs - float(args.fadeout or 0), 4)

	if args.crop:
		crop_params = args.crop.split(":")
		if len(crop_params) == 4:
			crop_width, crop_height, crop_x, crop_y = crop_params

	if args.height:
		if args.nvidia:
			filter_scale = f"scale_cuda=-1:{int(args.height)}"
		else:
			filter_scale = f"scale=-1:{int(args.height)}:flags=spline+accurate_rnd+full_chroma_int+full_chroma_inp"
	else:
		filter_scale = None

	# Just set all the important parameters and hope that's enough (if fixrgb > 0)
	opt_fixrgb = ["-colorspace", "bt709", "-color_range", "jpeg", "-color_primaries", "bt709", "-color_trc", "bt709"] if (int(args.fixrgb) or 0) > 0 else []

	# Force the video output to full range RGB as well (if fixrgb == 2)
	filter_fixrgb = "scale=in_range=tv:out_range=pc" if int(args.fixrgb) == 2 else None

	filter_vfadein = f"fade=t=in:st=0:d={args.fadein}" if args.fadein else None
	filter_vfadeout = f"fade=t=out:st={fadeout_start}:d={args.fadeout}" if args.fadeout else None

	if args.nvidia:
		if args.fadein and args.fadeout:
			# override if both fades are set to avoid multiple hwupload/hwdownloads
			filter_vfadein = f"hwdownload,format=nv12,{filter_vfadein}"
			filter_vfadeout = f"{filter_vfadeout},hwupload"
		else:
			filter_vfadein = f"hwdownload,format=nv12,{filter_vfadein},hwupload" if args.fadein else None
			filter_vfadeout = f"hwdownload,format=nv12,{filter_vfadeout},hwupload" if args.fadeout else None

	filter_avolume = f"volume={args.volume}" if args.volume else None
	filter_afadein = f"afade=t=in:st=0:d={args.fadein}:curve=ihsin" if args.fadein else None
	filter_afadeout = f"afade=t=out:st={fadeout_start}:d={args.fadeout}:curve=ihsin" if args.fadeout else None

	filter_crop = f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y}" if args.crop else None

	filter_vfade = ",".join(filter(None, [filter_vfadein, filter_vfadeout]))
	filter_audio = ",".join(filter(None, [filter_avolume, filter_afadein, filter_afadeout]))

	opt_metadata = ["-metadata", f"title=\"{args.title}\""] if args.title else []

	opt_framerate = ["-r", args.framerate] if args.framerate else []

	opt_vcodec = args.codec

	convert_audio = args.audio_force or args.volume or (args.fadein or args.fadeout)

	opt_acodec = ["-c:a", "aac", "-b:a", "384k"] if convert_audio else ["-c:a", "copy"]
	opt_audio = ["-an"] if args.mute else opt_acodec
	opt_afilter = ["-af", filter_audio] if filter_audio and not args.mute else []

	opt_duration = ["-t", f"{duration_secs:.4f}"] if args.t or args.to else []

	opt_vfilter_joined = ",".join(filter(None, [filter_crop, filter_scale, filter_fixrgb, filter_vfade]))
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
				   if args.youtube and not args.hardware else []

	opt_nv_hwaccel = "-hwaccel cuvid".split(" ") if args.nvidia else []
	opt_ap_hwaccel = "-hwaccel videotoolbox".split(" ") if args.apple else []

	CODEC_OPTIONS = {
		"libx264": f"-crf {CRF_X264} -preset {PRESET} -tune film -profile high -level 5.2".split(" ") + opt_fixrgb + opt_youtube,
		"libx265": f"-crf {CRF_X265} -preset {PRESET} -tune film -profile high -level 5.2".split(" "),
		"h264_cuvid": f"-preset {PRESET} -profile high -level 5.2 -rc constqp -qp {QP_NVENC} -strict_gop true -rc-lookahead 48 -spatial-aq true -temporal-aq true -aq-strength 8".split(" "),
		"h264_videotoolbox": f"-profile high -level 5.1 -coder cabac".split(" ")
	}

	ffmpeg_args = ["ffmpeg"] + \
						opt_nv_hwaccel + opt_ap_hwaccel + \
					   ["-ss", args.ss,
						"-i", f"{args.i}",
						"-c:v", args.codec] + \
						opt_audio + opt_afilter + \
						CODEC_OPTIONS[args.codec] + \
						opt_framerate + \
						opt_vfilter + opt_metadata + opt_duration + \
						(args.ffmpeg.split(" ") if args.ffmpeg else []) + \
						["-y", f"{args.out}"]

	if args.debug:
		print("#" * 40)

		print("Script arguments:\n", args)

		print("ffprobe output:", video_info)
		print("Start time in seconds:", f"{start_secs:.4f}")
		print("Duration in seconds:", f"{duration_secs:.4f}")
		print("Video fade filters:", filter_vfade)
		print("Audio filters:", filter_audio)

		if args.youtube:
			print("YouTube arguments:\n", " ".join(opt_youtube))

		print("ffmpeg arguments:\n", " ".join(ffmpeg_args))

		print("#" * 40)
		input("Press Enter to continue...")

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