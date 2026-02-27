from DDSim.DD4hepSimulation import DD4hepSimulation
from g4units import mm, GeV, MeV, degree

SIM = DD4hepSimulation()
SIM.gun.energy       = 2*GeV
SIM.gun.particle     = "e-"
SIM.gun.multiplicity = 1
SIM.gun.position     = (0.0, 0.0, 0.0)
SIM.gun.direction    = (0.0, 0.0, 1.0)
SIM.gun.distribution = "cos(theta)"
SIM.gun.thetaMin     = 45*degree
SIM.gun.thetaMax     = 135*degree

SIM.numberOfEvents = 100
