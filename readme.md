# auto_ffmpeg.py

## What's this?
This is a Python 3 script that aims to make some things that are complicated to do with ffmpeg easier.

## What is this not?
This isn't a script to make video encoding particularly efficient or video files particularly small. In fact, this script focuses more on video quality than on video size. If you're out to find the perfect size/quality ratio, this is not what you're looking for.

Also, unless you explicitly enable it, the encoding method that's used here won't use hardware acceleration. This means that if you process a long video file with this script, you most likely won't be able to use the computer for anything else for *a while*.
    
## All options, explained:
* `-i`: The input video file.
* `-ss`: The position in the input video to skip to before doing anything. Can be either a timestamp (supported formats are below) or a float (for seconds). Default is 0, starting at the beginning.
  * The supported timestamp formats are "%H:%M:%S.%f", "%H:%M:%S", "%M:%S.%f", and "%M:%S"
* `-t`: The duration of the output video. Supports the same arguments as `-ss`. Can't be used with `-to`.
  * `-to`: Stops the output video at this position. Supports the same arguments as `-ss`. Can't be used with `-t`.
* `-vt/--title`: The video title to be embedded in the output video's metadata. Must be enclosed in double quotes.
* `-m/--mute`: Mutes the output video. Takes no arguments.
* `-f/--fade`: Applies both a fade-in and a fade-out to the output video. The duration in seconds is expected as an integer or a float.
  * `-fi/--fadein`: Applies a fade-in to the output video. Takes the same arguments as `-f`. Is ignored if `-f` is present.
  * `-fo/--fadeout`: Applies a fade-out to the output video. Takes the same arguments as `-f`. Is ignored if `-f` is present.
* `-c/--crop`: Crops the video. Uses the same syntax as ffmpeg: `width:height:x:y`
* `-vh/--height`: Resizes the video to be this many pixels high using Lanczos interpolation, preserving the aspect ratio. Expects a positive integer argument.
  * The lack of an option to resize to a certain width is intentional.
* `-vc/--codec`: Accepts either "libx264" or "libx265". Default is "libx264".
* `-yt/--youtube`: Applies a bunch of options to make the video as YouTube-friendly as possible.  No more "This video needs to be in a streamable format" warnings. Only works with libx264 and can't be used with hardware acceleration.
* `-hw/--hardware`: Enables hardware acceleration for compatible Nvidia GPUs. Requires an ffmpeg build with support for the CUDA SDK, NVENC, and CUVID. Can't be used with `-yt`.
* `--fixrgb`: Basically a leftover command, but it might be useful for some. It accepts the integer values 1 or 2, depending on which it does this:
  * `1`: Nothing is converted, only the color metadata is inserted. Useful in cases where the source material is implied to contain full range video but isn't read as such by other programs.
  * `2`: `auto_ffmpeg.py` will assume that the source video has a limited RGB range and will force-convert it to full RGB range. Then, it will embed all necessary color metadata just to be safe.
* `--debug`: Prints some additional debugging info and requires a keypress before actually starting to process video files.

## About hardware acceleration:
If you enable hardware acceleration, videos will be processed much faster, but resulting files will be much larger as well.
On my PC, with an i7-6700K and a GTX 1070, downscaling an ~18 second 4K video to 720p and applying a fade out filter takes:
* about 33 seconds using libx264 on the CPU, resulting in a 19 MB file
* about 7 seconds when using the GPU, resulting in a 50 MB file
Don't be surprised if video files you create using hardware acceleration are three times as large as expected.

## Usage examples:
### Skip the first x seconds of a video
    ./auto_ffmpeg.py -i VIDEO_FILE -ss x OUT_FILE
### Only take the first x seconds of a video
    ./auto_ffmpeg.py -i VIDEO_FILE -t x OUT_FILE
### Start at 2:35 minutes and take the next 35.5 seconds
    ./auto_ffmpeg.py -i VIDEO_FILE -ss 2:35 -t 35.5 OUT_FILE
### Resize a video to be 720 pixels high, add a fade-out effect lasting 0.5 seconds, limit the video length to 30 seconds, and embed a video title
    ./auto_ffmpeg.py -i VIDEO_FILE -vh 720 -fo 0.5 -t 30 -vt "title goes here" OUT_FILE
### Add both a fade-in and a fade-out effect lasting half a second, limit the video to 50 seconds and prepare it for a YouTube upload
    ./auto_ffmpeg.py -i VIDEO_FILE -f 0.5 -t 50 -yt OUT_FILE