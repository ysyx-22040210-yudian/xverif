.PHONY: all xdebug xbit xentry xloc test full-test clean

all: xdebug xbit xentry xloc

xdebug:
	$(MAKE) -C xdebug

xbit:
	$(MAKE) -C xbit

xentry:
	$(MAKE) -C xentry

xloc:
	$(MAKE) -C xloc

test: xdebug xbit xentry xloc
	$(MAKE) -C xdebug schema-test
	$(MAKE) -C xdebug contract-test
	$(MAKE) -C xdebug unit-test
	$(MAKE) -C xbit test
	$(MAKE) -C xentry test
	$(MAKE) -C xloc test
	$(MAKE) -C xdebug/testdata/combined/active_driver fixture
	regression/run_xdebug_regression.sh

full-test: xdebug xbit xentry xloc
	$(MAKE) -C xbit test
	$(MAKE) -C xentry test
	$(MAKE) -C xloc test
	regression/run_full_regression.sh

clean:
	$(MAKE) -C xdebug clean
	$(MAKE) -C xbit clean
	$(MAKE) -C xentry clean
	$(MAKE) -C xloc clean
