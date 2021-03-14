#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import argparse
import time
import json
import math
from os.path import getsize
from datetime import datetime as dt
from tempfile import mkstemp

def closest(num, arr):
	filtered = filter(lambda x: x >= num, arr)
	return min(filtered)

def ceil_even(num):
	return math.ceil(num / 2.0) * 2

# from humanize package
def readable_size(value, binary=False, gnu=False, format="%.1f"):
	suffixes = {
		"decimal": ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"),
		"binary": ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"),
		"gnu": "KMGTPEZY",
	}

	if gnu:
		suffix = suffixes["gnu"]
	elif binary:
		suffix = suffixes["binary"]
	else:
		suffix = suffixes["decimal"]

	base = 1024 if (gnu or binary) else 1000
	bytes = float(value)
	abs_bytes = abs(bytes)

	if abs_bytes == 1 and not gnu:
		return "%d Byte" % bytes
	elif abs_bytes < base and not gnu:
		return "%d Bytes" % bytes
	elif abs_bytes < base and gnu:
		return "%dB" % bytes

	for i, s in enumerate(suffix):
		unit = base ** (i + 2)
		if abs_bytes < unit and not gnu:
			return (format + " %s") % ((base * bytes / unit), s)
		elif abs_bytes < unit and gnu:
			return (format + "%s") % ((base * bytes / unit), s)
	if gnu:
		return (format + "%s") % ((base * bytes / unit), s)
	return (format + " %s") % ((base * bytes / unit), s)

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
							# "-select_streams", "v:0",
							"-hide_banner",
							"-print_format", "json",
							# "-loglevel", "quiet",
							"-show_entries", "stream=width,height,duration,r_frame_rate"]

	p = subprocess.Popen(ffprobe_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

	ffprobe_output = p.stdout.read()
	ffprobe_json = json.loads(ffprobe_output)

	if "streams" not in ffprobe_json:
		if debug:
			print(f"ffprobe args: {ffprobe_args}")
			print(f"ffprobe output: {ffprobe_output}")
		raise RuntimeError("ffprobe failed.")

	stream = ffprobe_json["streams"][0]
	try:
		if "/" in stream["r_frame_rate"]:
			dividend, divisor = stream["r_frame_rate"].split("/")
			stream["r_frame_rate"] = int(dividend)/int(divisor)
	except Exception as e:
		if len(ffprobe_json["streams"]) < 2:
			raise e

		stream = ffprobe_json["streams"][1]
		if "/" in stream["r_frame_rate"]:
			dividend, divisor = stream["r_frame_rate"].split("/")
			stream["r_frame_rate"] = int(dividend)/int(divisor)


	if "duration" in stream:
		stream["duration"] = float(stream["duration"])
	else:
		print("Falling back to duration heuristics")
		for s in ffprobe_json["streams"]:
			if "duration" in s:
				stream["duration"] = float(s["duration"])
				print(f"Found duration: {stream['duration']}")
				break

		if not "duration" in stream:
			print("You are most likely opening a faulty WEBM file. Be aware that -t and -to will most likely not do what you expect.")
			stream["duration"] = 1000.0

	return stream

def start_ffmpeg(args, debug):
	if debug:
		print("#" * 40)
		print("Script arguments:")
		print(" ".join(args))
		print("#" * 40)
		input("Press Enter to continue...")

	start = time.time()

	p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

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
				return False, p.returncode

			break

		if line != oldline:
			print(line)

		oldline = line

	return True, 0

def main():
	FAST_SEEK = False

	CRF_X264 = 17
	CRF_X265 = 22
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

	parser = argparse.ArgumentParser(description="Automate ffmpeg stuff")
	parser.add_argument("-i", metavar="input", type=str, required=True, help="Input file")
	parser.add_argument("-ss", metavar="start time", type=str, default="0", help="Start time")

	duration_group = parser.add_mutually_exclusive_group()
	duration_group.add_argument("-t", metavar="duration", type=str, default=None, help="Duration")
	duration_group.add_argument("-to", metavar="position", type=str, default=None, help="Position")

	audio_group = parser.add_mutually_exclusive_group()
	audio_group.add_argument("-m", "--mute", action="store_true", help="Mute audio")
	audio_group.add_argument("-af", "--audio-force", action="store_true", help="Force convert audio")
	audio_group.add_argument("-av", "--volume", metavar="volume", type=str, default=None, help="Audio volume adjustment factor")
	audio_group.add_argument("-n", "--normalize", action="store_true", help="Normalize volume")

	size_group = parser.add_mutually_exclusive_group()
	size_group.add_argument("-vw", "--width", metavar="width", type=str, default=None, help="New video width (keeps aspect ratio)")
	size_group.add_argument("-vh", "--height", metavar="height", type=str, default=None, help="New video height (keeps aspect ratio)")

	parser.add_argument("-vt", "--title", metavar="title", type=str, default=None, help="Video title")
	parser.add_argument("-f", "--fade", metavar="duration", type=str, default=None, help="Fade in/out duration in seconds. Takes priority over -fi and -fo")
	parser.add_argument("-fi", "--fadein", metavar="duration", type=str, default=None, help="Fade in duration in seconds")
	parser.add_argument("-fo", "--fadeout", metavar="duration", type=str, default=None, help="Fade out duration in seconds")
	parser.add_argument("-c", "--crop", metavar="w:h:x:y", type=str, default=None, help="New video region")
	parser.add_argument("-r", "--framerate", metavar="framerate", type=str, default=None, help="New video frame rate")
	parser.add_argument("-l", "--loop", metavar="loop", type=str, default=None, help="Video loop count")
	parser.add_argument("-sf", "--slowmo-fps", metavar="framerate", type=str, default=None, help="Upsampled frame rate")
	parser.add_argument("-sm", "--slowmo-mode", type=str, default="sensible", choices=["slow", "sensible", "fast"], help="Upsampling preset")
	parser.add_argument("-ff", "--ffmpeg", metavar="args", type=str, default=None, help="Passthrough arguments for ffmpeg")
	parser.add_argument("-fs", "--fast-seek", action="store_true", help="Force-enables fast seek")

	parser.add_argument("--brightness", metavar="brightness", type=float, default=0.0, help="Brightness adjustment (default 0.0)")
	parser.add_argument("--contrast", metavar="contrast", type=float, default=1.0, help="Contrast adjustment (default 1.0)")
	parser.add_argument("--saturation", metavar="saturation", type=float, default=1.0, help="Saturation adjustment (default 1.0)")
	parser.add_argument("--sharpen", action="store_true", help="Sharpen the output image")

	parser.add_argument("-gc", "--gif-colors", metavar="colors", type=str, default="256", help="Number of colors to use when generating a GIF palette")
	parser.add_argument("-gd", "--gif-dither", type=str, default="floyd_steinberg", choices=["none", "bayer", "heckbert", "floyd_steinberg", "sierra2", "sierra2_4a"], help="GIF dither algorithm to use")
	parser.add_argument("-gs", "--gif-stats", type=str, default="diff", choices=["single", "diff", "full"], help="palettegen stats_mode parameter")
	parser.add_argument("-gt", "--gif-transparency", action="store_true", help="Enable GIF transparency")

	parser.add_argument("-g", "--garbage", action="store_true", help="Garbage mode (lowers bitrate to shrink video files)")
	parser.add_argument("--fixrgb", type=str, metavar="mode", default="0", choices=["0", "1", "2"], help="Convert TV RGB range to PC RGB range (hacky)")
	parser.add_argument("--debug", action="store_true", help="Debug mode (displays lots of additional information)")

	extra_group = parser.add_mutually_exclusive_group()
	extra_group.add_argument("-yt", "--youtube", action="store_true", help="YouTube mode (adds options to make YouTube happy)")
	extra_group.add_argument("-nv", "--nvidia",  action="store_true", help="Enable hardware acceleration for Nvidia GPUs (experimental)")

	extra_group.add_argument("--x264", action="store_true", help="Use libx264")
	extra_group.add_argument("--x265", action="store_true", help="Use libx265")
	extra_group.add_argument("--gif",  action="store_true", help="Create an animated GIF")
	extra_group.add_argument("--apng", action="store_true", help="Create an animated PNG")
	extra_group.add_argument("--webp", action="store_true", help="Create an animated WebP image (untested)")

	parser.add_argument("out", type=str, help="out file")

	args = parser.parse_args()

	video_info = get_video_info(args.i, args.debug)

	start_secs = parse_ffmpeg_timestamp(args.ss, args.debug)
	if args.to:
		duration_secs = parse_ffmpeg_timestamp(args.to, args.debug) - start_secs
	elif args.t:
		duration_secs = parse_ffmpeg_timestamp(args.t, args.debug)
	else:
		duration_secs = video_info["duration"] - start_secs

	if args.youtube or args.x264:
		args.codec = "libx264"
	elif args.x265:
		args.codec = "libx265"
	elif args.nvidia:
		args.codec = "h264_cuvid"
	elif args.gif:
		args.codec = "gif"
	elif args.apng:
		args.codec = "apng"
	elif args.webp:
		args.codec = "libwebp"
	else:
		args.codec = "libx264" # default codec

	if args.garbage:
		CRF_X264 = int(CRF_X264 * 1.6)
		CRF_X265 = int(CRF_X265 * 1.6)

	if args.gif or args.fast_seek:
		# for GIF creation, fast seek needs to be enabled
		FAST_SEEK = True

	if args.fade:
		args.fadein = args.fade
		args.fadeout = args.fade

	if FAST_SEEK:
		fadein_start  = 0
		fadeout_start = round(duration_secs - float(args.fadeout or 0), 4)
	else:
		fadein_start  = round(start_secs, 4)
		fadeout_start = round(start_secs + duration_secs - float(args.fadeout or 0), 4)

	if args.crop:
		crop_params = args.crop.split(":")
		if len(crop_params) == 4:
			crop_width, crop_height, crop_x, crop_y = crop_params
		else:
			raise RuntimeError("welp")

	loop_amount = 0
	if args.loop:
		loop_amount = abs(int(args.loop)) - 1

	if args.width or args.height:
		new_size = args.width or args.height

		if args.width:
			video_size = float(video_info["width"])
		elif args.height:
			video_size = float(video_info["height"])

		if new_size.lower().endswith("x"):
			new_size_parsed = int(video_size * float(new_size[:-1]))
		else:
			new_size_parsed = int(new_size)

		new_size_parsed = ceil_even(new_size_parsed)

		if args.width:
			size_str = f"{new_size_parsed}:-2"
		elif args.height:
			size_str = f"-2:{new_size_parsed}"

		if args.nvidia:
			filter_scale = f"scale_cuda={size_str}"
		else:
			filter_scale = f"scale={size_str}:flags=spline+accurate_rnd+full_chroma_int+full_chroma_inp"
	else:
		filter_scale = None

	# Just set all the important parameters and hope that's enough (if fixrgb > 0)
	opt_fixrgb = ["-colorspace", "bt709", "-color_range", "jpeg", "-color_primaries", "bt709", "-color_trc", "bt709"] if (int(args.fixrgb) or 0) > 0 else []

	# Force the video output to full range RGB as well (if fixrgb == 2)
	filter_fixrgb = "scale=in_range=tv:out_range=pc" if int(args.fixrgb) == 2 else None

	filter_vfadein = f"fade=t=in:st={fadein_start}:d={args.fadein}" if args.fadein else None
	filter_vfadeout = f"fade=t=out:st={fadeout_start}:d={args.fadeout}" if args.fadeout else None

	transparency = "1" if args.gif_transparency else "0"
	filter_palettegen = f"palettegen=stats_mode={args.gif_stats}:reserve_transparent={transparency}:max_colors={args.gif_colors}" if args.gif else None
	filter_paletteuse = f"paletteuse=diff_mode=rectangle:bayer_scale=1:dither={args.gif_dither}"

	if args.nvidia:
		if args.fadein and args.fadeout:
			# override if both fades are set to avoid multiple hwupload/hwdownloads
			filter_vfadein = f"hwdownload,format=nv12,{filter_vfadein}"
			filter_vfadeout = f"{filter_vfadeout},hwupload"
		else:
			filter_vfadein = f"hwdownload,format=nv12,{filter_vfadein},hwupload" if args.fadein else None
			filter_vfadeout = f"hwdownload,format=nv12,{filter_vfadeout},hwupload" if args.fadeout else None

	filter_avolume = f"volume={args.volume}" if args.volume else None
	filter_normalize = "dynaudnorm=correctdc=1:altboundary=1" if args.normalize else None
	filter_afadein = f"afade=t=in:st={fadein_start}:d={args.fadein}:curve=losi" if args.fadein else None
	filter_afadeout = f"afade=t=out:st={fadeout_start}:d={args.fadeout}:curve=losi" if args.fadeout else None

	# minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bilat:me=esa:search_param=32:vsbmc=1
	ME_MODES = {
		"fast": "hexbs",
		"sensible": "umh",
		"slow": "esa"
	}
	ME_RANGES = {
		"fast": "8",
		"sensible": "16",
		"slow": "24"
	}
	filter_minterpolate = f"minterpolate=fps={args.slowmo_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bilat:me={ME_MODES[args.slowmo_mode]}:search_param={ME_RANGES[args.slowmo_mode]}:vsbmc=1" if args.slowmo_fps else None

	filter_fps = f"fps=fps={args.framerate}" if args.framerate else None

	filter_crop = f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y}" if args.crop else None

	filter_loop = f"loop=loop={loop_amount}:size=32767:start=0"

	filter_eq = f"eq=brightness={args.brightness}:saturation={args.saturation}:contrast={args.contrast}"

	filter_sharpen = "unsharp" if args.sharpen else None

	filter_vfade = ",".join(filter(None, [filter_vfadein, filter_vfadeout]))
	filter_audio = ",".join(filter(None, [filter_avolume, filter_normalize, filter_afadein, filter_afadeout]))

	opt_passthrough = args.ffmpeg.split(" ") if args.ffmpeg else []

	opt_metadata = ["-metadata", f"title=\"{args.title}\""] if args.title else []

	opt_global = "-loglevel warning -hide_banner".split(" ")

	convert_audio = args.audio_force or (filter_audio != None)

	opt_acodec_bitrate = "128k" if args.garbage else "256k"
	opt_acodec = ["-c:a", "aac", "-b:a", opt_acodec_bitrate] if convert_audio else ["-c:a", "copy"]
	opt_audio = ["-an"] if args.mute or args.gif else opt_acodec
	opt_afilter = ["-af", filter_audio] if filter_audio and not args.mute else []

	opt_duration = ["-t", f"{duration_secs:.4f}"] if args.t or args.to else []

	opt_vfilter_joined = ",".join(filter(None, [filter_fps, filter_fixrgb, filter_crop, filter_scale, filter_minterpolate, filter_eq, filter_sharpen, filter_loop, filter_vfade, filter_palettegen]))
	opt_vfilter = ["-vf", opt_vfilter_joined] if opt_vfilter_joined else []

	if args.youtube:
		yt_index1 = closest(video_info["r_frame_rate"], YT_BITRATES.keys())
		yt_index2 = closest(video_info["height"], YT_BITRATES[yt_index1].keys())
		yt_bitrate = YT_BITRATES[yt_index1][yt_index2]
		opt_youtube = ["-movflags", "+faststart",
					   "-maxrate", yt_bitrate,
					   "-bufsize", f"{round(int(yt_bitrate[:-1])*1.5)}M",
					   "-g", f"{video_info['r_frame_rate'] / 2}",
					   "-bf", "2",
					   "-pix_fmt", "yuv420p"] \
					   if args.youtube else []
	else:
		opt_youtube = []

	opt_nv_hwaccel = "-hwaccel cuvid".split(" ") if args.nvidia else []
	opt_hardware = opt_nv_hwaccel

	CODEC_OPTIONS = {
		"libx264": f"-crf {CRF_X264} -preset {PRESET} -pix_fmt yuv420p -tune film -profile:v high -level 5.2".split(" ") + opt_fixrgb + opt_youtube,
		"libx265": f"-crf {CRF_X265} -preset {PRESET}".split(" "),
		"h264_cuvid": f"-preset {PRESET} -profile:v high -level 5.2 -rc constqp -qp {QP_NVENC} -strict_gop true -rc-lookahead 48 -spatial-aq true -temporal-aq true -aq-strength 8".split(" "),
		"gif": f"-f gif -loop 0".split(" "),
		"apng": f"-f apng -plays 0".split(" "),
		"libwebp": f"-f webp -loop 0".split(" ")
	}

	opts_seek  = ["-ss", str(round(start_secs, 4))] if args.ss != "0" else []
	opts_input = ["-i", args.i]
	if FAST_SEEK:
		opt_input = opts_seek + opts_input
	else:
		opt_input = opts_input + opts_seek

	opt_input += opt_duration
	opt_codec = CODEC_OPTIONS[args.codec]

	if args.gif:
		# exporting a GIF
		_, palette_file = mkstemp(prefix="palette_", suffix=".png")
		ffmpeg_args = ["ffmpeg"] + opt_global + \
						opt_input + \
						["-c:v", args.codec] + opt_codec + \
						opt_audio + opt_afilter + \
						opt_vfilter + opt_metadata + opt_passthrough + \
						["-y", palette_file]
		print("Creating GIF palette…")
	else:
		# exporting a video, an APNG, or an animated WebP image
		ffmpeg_args = ["ffmpeg"] + opt_global + \
						opt_hardware + opt_input + \
						["-c:v", args.codec] + opt_codec + \
						opt_audio + opt_afilter + \
						opt_vfilter + opt_metadata + opt_passthrough + \
						["-y", args.out]
		print("Encoding output file…")

	# first pass
	success, returncode = start_ffmpeg(ffmpeg_args, args.debug)
	if not success:
		print(f"ffmpeg exited with code {returncode}.")
		sys.exit(returncode)

	# do second GIF creation pass
	if args.gif:
		print("Creating GIF…")

		if FAST_SEEK:
			opt_input = opts_seek + ["-i", args.i, "-i", palette_file] + opt_duration
		else:
			opt_input = ["-i", args.i, "-i", palette_file] + opts_seek + opt_duration

		# opt_input = ["-i", args.i, "-i", palette_file]

		opt_vfilter_joined = ",".join(filter(None, [filter_fps, filter_fixrgb, filter_crop, filter_scale, filter_minterpolate, filter_eq, filter_sharpen, filter_vfade, filter_paletteuse]))
		opt_vfilter = ["-lavfi", opt_vfilter_joined] if opt_vfilter_joined else []

		ffmpeg_args = ["ffmpeg"] + opt_global + \
						opt_input + \
						["-c:v", args.codec] + opt_codec + \
						opt_audio + opt_afilter + \
						opt_vfilter + opt_metadata + opt_passthrough + \
						["-y", args.out]

		success, returncode = start_ffmpeg(ffmpeg_args, args.debug)
		if not success:
			print(f"ffmpeg exited with code {returncode}.")
			sys.exit(returncode)

		# clean up
		os.remove(palette_file)

	try:
		out_size = getsize(args.out)
		size_decimal = readable_size(out_size)
		size_binary = readable_size(out_size, binary=True)

		out_msg = f"Output file size: {size_decimal}/{size_binary}"
		if out_size < 8388120: # magic number: max allowed file size on discord
			print(f"{out_msg} (Discord safe)")
		else:
			print(f"{out_msg}")
	except Exception as e:
		print("ERROR: Couldn't determine output file size!")

if __name__ == '__main__':
	main()