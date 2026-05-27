VERDI_HOME ?= $(shell echo $$VERDI_HOME)

ifeq ($(VERDI_HOME),)
$(error VERDI_HOME environment variable is not set)
endif

NPI_INC     = $(VERDI_HOME)/share/NPI/inc
NPI_L1_INC  = $(VERDI_HOME)/share/NPI/L1/C/inc
NPI_LIB     = $(VERDI_HOME)/share/NPI/lib/LINUX64

NPI_CXXFLAGS = -I$(NPI_INC) -I$(NPI_L1_INC)
NPI_LDFLAGS  = -L$(NPI_LIB) -Wl,-rpath-link,$(NPI_LIB) -lNPI -lnpiL1 -ldl -lrt -lz
