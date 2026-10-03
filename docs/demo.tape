# Terminal recording for the README. Render from the repo root:
#
#   vhs docs/demo.tape
#
# Needs vhs (https://github.com/charmbracelet/vhs) plus its ttyd and ffmpeg
# dependencies, and `uv sync` already run. The output is the real CLI's real
# output on synthetic dumps from tools/gen_fixtures.py (generated, unrecorded,
# with its fixed default seed); nothing here is scripted text.
#
# vhs 0.12 with ffmpeg 9 exits 0 but silently writes no GIF (its own ffmpeg
# call fails). Workaround: point Output at a directory ("Output frames/") to
# get PNG frames, then assemble them yourself:
#
#   ffmpeg -framerate 50 -i frames/frame-text-%05d.png \
#     -framerate 50 -i frames/frame-cursor-%05d.png \
#     -filter_complex "[0][1]overlay,crop=iw:1260:0:0,scale=iw/2:-2:flags=lanczos,pad=iw+48:ih+48:24:24:color=0x171717,tpad=stop_mode=clone:stop_duration=6,fps=12,split[a][b];[a]palettegen[p];[b][p]paletteuse" \
#     docs/demo.gif
#
# On a Retina display the frames come out at 2x; the filter crops the empty
# rows below the output, scales back to 1x, adds padding, and holds the final
# frame for 6 seconds so the result can be read.

Output docs/demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 1560
Set Height 760
Set Padding 24
Set TypingSpeed 45ms

# Start from a clean state (not recorded): a short prompt on its own line, an
# up-to-date environment so uv prints nothing, and freshly generated fixtures.
Hide
Type `export PS1=$'\n$ ' && cd $(git rev-parse --show-toplevel) && uv sync -q && rm -rf demo_data demo_output && uv run python tools/gen_fixtures.py --out-dir demo_data > /dev/null && clear`
Enter
Show

Type "head -5 demo_data/regular/dump_003.txt"
Sleep 400ms
Enter
Sleep 3s

Type "uv run dump-parser demo_data/regular -o demo_output/results --report demo_output/report.md"
Sleep 600ms
Enter
Sleep 4s

Type "head -4 demo_output/results.csv"
Sleep 400ms
Enter

# Hold on the result.
Sleep 4s
