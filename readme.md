# ffauto.py

## What's this?
This is a Python 3 script that aims to be a "swiss army knife" script for some common ffmpeg tasks.

## What is this not?
This isn't a script to make video encoding particularly efficient or video files particularly small. In fact, this script focuses more on video quality than on video size. If you're out to find the perfect size/quality ratio, this is not what you're looking for.

Also, unless you explicitly enable it, the encoding method that's used here won't use hardware acceleration. This means that if you process a long video file with this script, you most likely won't be able to use the computer for anything else for *a while*.

## All of `ffauto`'s options

### Required options

* `-i`: The input video file.
* `out`: The output file. Must be the last parameter.

### General options

* `-ss`: The position in the input video to skip to before doing anything. Can be either a timestamp (supported formats are below) or a float (for seconds).
	* The supported timestamp formats are `%H:%M:%S.%f`, `%H:%M:%S`, `%M:%S.%f`, `%M:%S`, `%S.%f`, and `%S`.
* `-t`: The duration of the output video. Supports the same arguments as `-ss`. Can't be used with `-to`.
* `-to`: Stops the output video at this position. Supports the same arguments as `-ss`. Can't be used with `-t`.
* `-vt/--title`: The video title to be embedded in the output video's metadata. Must be enclosed in double quotes.
* `-gp/--gif-palette`: The number of colors to use when creating an animated GIF. Ignored if `--gif` isn't specified.
* `-ff/--ffmpeg`: Passthrough arguments for ffmpeg.

### Video options
#### All options listed in this category are applied in the order of appearance.

* `-r/--framerate`: Changes the output video's framerate. Expects a positive number.
* `--fixrgb`: A leftover command, but it might be useful for some. It accepts the integer values 1 or 2, depending on which it does this:
	* `1`: Nothing is converted, only the color metadata is inserted. Useful in cases where the source material is implied to contain full range video but isn't read as such by other programs.
	* `2`: `ffauto.py` will assume that the source video has a limited RGB range and will force-convert it to full RGB range. Then, it will embed all necessary color metadata just to be safe.
* `-c/--crop`: Crops the video. Uses the same syntax as ffmpeg: `width:height:x:y`
* `-vh/--height`: Resizes the video to be this many pixels high, preserving the aspect ratio. Expects a positive number. Final video height is rounded to the next even number.
	* To use scaling factors instead of absolute pixel heights, append an "x" to the argument. For example, `-vh 0.5x` will halve a video's height.
* `-f/--fade`: Applies both a fade-in and a fade-out to the output video. The duration in seconds is expected as a number.
	* `-fi/--fadein`: Applies a fade-in to the output video. Takes the same arguments as `-f`. Is ignored if `-f` is present.
	* `-fo/--fadeout`: Applies a fade-out to the output video. Takes the same arguments as `-f`. Is ignored if `-f` is present.

### Audio options

* `-m/--mute`: Mutes the output video. Takes no arguments.
* `-av/--volume`: Changes the audio volume by a specified factor. Expects a positive number.
* `-af/--audio-force`: Forces audio reencoding.

### Format Options, mutually exclusive

* `-yt/--youtube`: Applies a bunch of options to make the video as YouTube-friendly as possible. No more "This video needs to be in a streamable format" warnings. Will set the codec to H.264.
* `-nv/--nvidia`: Enables hardware acceleration for compatible Nvidia GPUs. Requires an ffmpeg build with support for the CUDA SDK, NVENC, and CUVID.
* `--x264`: Tells ffmpeg to use the `libx264` encoder. **(Default)**
* `--x265`: Tells ffmpeg to use the `libx265` encoder.
* `--gif`: Creates an animated GIF from the input video.
* `--apng`: Creates an animated PNG from the input video
* `--webp`: Creates an animated WebP image from the input video. **(Untested)**


### Debugging commands


* `--debug`: Prints some additional debugging info and requires a keypress before actually starting to process video files.

## About hardware acceleration:
If you enable hardware acceleration, videos will be processed much faster, but resulting files will be much larger as well.
On my PC, with an i7-6700K and a GTX 1070, downscaling an ~18 second 4K video to 720p and applying a fade out filter takes:
* about 33 seconds using libx264 on the CPU, resulting in a 19 MB file
* about 7 seconds when using the GPU, resulting in a 50 MB file

Don't be surprised if video files you create using hardware acceleration are three times as large as expected.

## Usage examples:
### Skip the first x seconds of a video
	./ffauto.py -i VIDEO_FILE -ss x OUT_FILE
### Only take the first x seconds of a video
	./ffauto.py -i VIDEO_FILE -t x OUT_FILE
### Start at 2:35 minutes and take the next 35.5 seconds
	./ffauto.py -i VIDEO_FILE -ss 2:35 -t 35.5 OUT_FILE
### Resize a video to be 720 pixels high, add a fade-out effect lasting 0.5 seconds, limit the video length to 30 seconds, and embed a video title
	./ffauto.py -i VIDEO_FILE -vh 720 -fo 0.5 -t 30 -vt "title goes here" OUT_FILE
### Add both a fade-in and a fade-out effect lasting half a second, limit the video to 50 seconds and prepare it for a YouTube upload
	./ffauto.py -i VIDEO_FILE -f 0.5 -t 50 -yt OUT_FILE