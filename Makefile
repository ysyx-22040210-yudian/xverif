.PHONY: all xdebug xbit xloc test full-test clean

all: xdebug xbit xloc

xdebug:
	$(MAKE) -C xdebug

xbit:
	$(MAKE) -C xbit

xloc:
	$(MAKE) -C xloc

test: xdebug xbit xloc
	$(MAKE) -C xdebug schema-test
	$(MAKE) -C xdebug contract-test
	$(MAKE) -C xdebug unit-test
	$(MAKE) -C xbit test
	$(MAKE) -C xloc test
	$(MAKE) -C xdebug/testdata/combined/active_driver fixture
	regression/run_xdebug_regression.sh

full-test: xdebug xbit xloc
	$(MAKE) -C xbit test
	$(MAKE) -C xloc test
	regression/run_full_regression.sh

clean:
	$(MAKE) -C xdebug clean
	$(MAKE) -C xbit clean
	$(MAKE) -C xloc clean
