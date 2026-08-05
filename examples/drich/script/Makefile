
# Compiler
CXX := g++
TARGET := dRICHAna dRICHAna_bootstrap
PODIO_PREFIX ?= /opt/local
# Compiler flags
CXXFLAGS := -std=c++20 -Wall -Wno-deprecated -I$(shell root-config --incdir) $(shell root-config --glibs) -L$(PODIO_PREFIX)/lib -lpodio -lpodioRootIO -ledm4hep -ledm4eic -I$(PODIO_PREFIX)/include

dRICHAna: dRICHAna.cpp dRICHAna_bootstrap.cpp
	$(CXX) -o dRICHAna dRICHAna.cpp $(CXXFLAGS)
	$(CXX) -o dRICHAna_bootstrap dRICHAna_bootstrap.cpp $(CXXFLAGS)

# Rule to clean the project
clean:
	rm -f $(TARGET)
