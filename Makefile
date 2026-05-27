.PHONY: all xdebug test full-test clean

all: xdebug

xdebug:
	$(MAKE) -C xdebug

test: xdebug
	$(MAKE) -C xdebug unit-test
	$(MAKE) -C xdebug/testdata/combined/active_driver fixture
	regression/run_xdebug_regression.sh

full-test: xdebug
	regression/run_full_regression.sh

clean:
	$(MAKE) -C xdebug clean
