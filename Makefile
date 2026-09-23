.PHONY: demo demo-big demo-clean

# One-command, end-to-end demo: generates a synthetic dataset (never real
# data), runs the full pipeline over it with redaction + the exposure report
# on by default, and writes CSV/report into the gitignored demo_output/.
demo:
	uv run python tools/gen_fixtures.py --out-dir demo_data
	@mkdir -p demo_output
	uv run dump-parser demo_data/regular \
		-o demo_output/results \
		--report demo_output/report.md \
		--scheduler synchronous \
		--no-summary
	@uv run python tools/demo_summary.py --demo-data demo_data --demo-output demo_output

# Exercises --blocksize (newline-aligned intra-file block splitting) against
# the one large generated file -- the thing the README describes at length
# but the regular `demo` target (many small files) doesn't demonstrate.
demo-big:
	uv run python tools/gen_fixtures.py --out-dir demo_data
	@mkdir -p demo_output
	uv run dump-parser demo_data/big \
		--blocksize 512KB \
		-o demo_output/big_results \
		--scheduler processes

demo-clean:
	rm -rf demo_data demo_output
