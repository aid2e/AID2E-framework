
# Compiler
CXX := g++
# Compiler flags
CXXFLAGS := -Wall -Wno-deprecated -I$(shell root-config --incdir) $(shell root-config --glibs) -L/opt/local/lib -lpodio -lpodioRootIO -ledm4hep -ledm4eic -I/opt/local/include

dRICHAna: dRICHAna.cpp dRICHAna_bootstrap.cpp
	$(CXX) -o dRICHAna dRICHAna.cpp $(CXXFLAGS)
	$(CXX) -o dRICHAna_bootstrap dRICHAna_bootstrap.cpp $(CXXFLAGS)

# Rule to clean the project
clean:
	rm -f $(OBJS) $(TARGET)
