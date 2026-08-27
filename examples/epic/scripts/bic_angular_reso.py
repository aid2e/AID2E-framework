"""Compute angular resolution of BIC AstroPix layers

This example script runs a simple calculation to compute the angular resolution
of the BIC AstroPix (imaging) layers for a specified particle species. Used in
the BIC example of an ePIC workflow.

Must be run inside the eic-shell. To install following instructions here:

    https://eic.github.io/tutorial-setting-up-environment/

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
"""

import argparse as ap
import json
import numpy as np
import sys
from dataclasses import dataclass
from typing import Dict

import ROOT
from podio.reading import get_reader


# =============================================================================
# Helper classes for the calculation
# ============================================================================= 

@dataclass
class Options:
    """Options for calculation

    Attributes:
        ifiles: list of input files
        ofile: output file
        excludes: list of layer indices to exclude 
        angle: angular coordinate to use (theta, eta, ...)
        pdg: PDG code to use (optional)
        hits: input reco hit collection
        pars: input MC particle collection
        assocs: input cluster-particle associations
    """
    ifiles: list[str]
    ofile: str
    excludes: list[int]
    angle: str = "eta"
    pdg: int = 11
    hits: str = "EcalBarrelImagingRecHits"
    pars: str = "MCParticles"
    assocs: str = "EcalBarrelImagingClusterAssociations"

    def set_opts_from_args(self, args):
        """Set optional members from CLI arguments"""
        self.angle  = args.angle
        self.pdg    = args.pdg
        self.hits   = args.hits
        self.pars   = args.pars
        self.assocs = args.assocs

# default options
DEFAULT_OPTS = Options(
    ifiles = ["root://dtn-eic.jlab.org//volatile/eic/EPIC/RECO/26.02.0/epic_craterlake/SINGLE/e-/5GeV/45to135deg/e-_5GeV_45to135deg.0099.eicrecon.edm4eic.root"],
    ofile = "e-_5GeV_45to135deg.0099.angreso.hist.root",
    excludes = [],
)


@dataclass
class Info:
    """Hit and Particle Info

    Helper class to store key information
    on hits and particles

    Attributes:
        energy: energy of hit/particle
        angle: anglular coordinate (theta, eta, ...)
        perp: radial coordinate (r/pt) of hit/particle
        layer: most upstream layer with hits
        vector: 3D position/momentum of hit/particle
    """
    energy: float = -999.0
    angle: float = -999.0
    perp: float = -999.0
    layer: int = -999
    vector: ROOT.Math.XYZVector = ROOT.Math.XYZVector(-999.0, -999.0, -999.0)

    def _set_vector(self, edmvec):
        """Set position vector from an edm4hep::Vector3f"""
        self.vector = ROOT.Math.XYZVector(
            edmvec.x,
            edmvec.y,
            edmvec.z
        )

    def _set_angle(self, coord):
        """Set angle based on provided angular coordinate name"""
        match coord:
            case "theta":
                self.angle = self.vector.Theta()
            case "eta":
                self.angle = self.vector.Eta()
            case "phi":
                self.angle = self.vector.Phi()
            case _:
                raise ValueError("Unknown coordinate specified!")

    def set_par_info(self, cname, par):
        """Extract info from an edm4hep::MCParticle"""
        self._set_vector(par.getMomentum())
        self._set_angle(cname)
        self.energy = par.getEnergy()
        self.perp   = self.vector.Rho()

    def set_hit_info(self, cname, hit):
        """Extract info from an edm4eic::CalorimeterHit"""
        self._set_vector(hit.getPosition())
        self._set_angle(cname)
        self.energy = hit.getEnergy()
        self.perp   = self.vector.Rho()
        self.layer  = hit.getLayer()

# =============================================================================
# Angular Resolution Calculation
# ============================================================================= 

def CalculateHitAngReso(opts: Options = DEFAULT_OPTS) -> Dict[str, float]:
    """Calculate angular resolution

    A function to calculate angular resolution for a 
    specified species of particle from BIC imaging
    hits according to this algorithm:

        1. Find the imaging cluster associated to thrown
           electron
        2. Locate the most energetic hit in each layer
           of the imaging cluster
        3. From these, select the hit in the most
           upstream layer and calculate the difference
           in angle
        4. Fit the main peak of the distribution of
           differences and extract the RMS of the
           peak
        5. Return the RMS as the resolution

    Args:
        opts: calculation options

    Returns:
        Dictionary of {key, value} where
        - key: the name of the objective associated with this script,
          in this case "resolution"
        - value: the value of the objective, in this case the RMS of
          the fit to the mc-reco differences
    """

    # sanitize coordinate input
    coord = opts.angle
    coord = coord.lower()

    # set up histograms, etc. -------------------------------------------------

    # set variable for axis accordingly 
    var = "x"
    match coord:
        case "theta":
            var = "#theta"
        case "eta":
            var = "#eta"
        case "phi":
            var = "#phi"
        case _:
            raise ValueError("Unknown coordinate specified!")

    # construct axis title
    axis = ";#delta" + var + " = " + var + "^{image}_{max hit} - " + var + "_{par}"

    # create histogram from extracting resolution
    hdiff = ROOT.TH1D("hAngRes", axis, 80, -0.2, 0.2)
    hdiff.Sumw2()

    # event loops -------------------------------------------------------------

    # loop through input files
    for ifile in opts.ifiles:

        # loop through all events
        reader = get_reader(ifile)
        for iframe, frame in enumerate(reader.get("events")):

            # grab relevant branches
            rehits = frame.get(opts.hits)
            mcpars = frame.get(opts.pars)
            assocs = frame.get(opts.assocs)

            # pick out the primary particle
            primary = None
            for par in mcpars:
                status = par.getGeneratorStatus()
                if par.getPDG() == opts.pdg and status == 1:
                    primary = par
                    break

            # if for some reason no primary was found,
            # skip event
            if primary is None:
                print(f"Warning! Frame {iframe} has no primary in file:\n  -- {ifile}")
                continue

            # scrape particle info for histogramming
            pinfo = Info()
            pinfo.set_par_info(coord, primary)

            # dictionaries to keep track of max energy
            # hits in each layer
            maxenes = {
                1 : 0.0,
                2 : 0.0,
                3 : 0.0,
                4 : 0.0,
                5 : 0.0,
                6 : 0.0
            }
            maxhits = dict()

            # now identify the most energetic hit in
            # each layer associated with the primary
            cluster = None
            for assoc in assocs:

                if primary != assoc.getSim():
                    continue
                else:
                    cluster = assoc.getRec()

                # loop through hits to check layers
                for hit in assoc.getRec().getHits():

                    layer = hit.getLayer()
                    if layer > 6:
                        print(f"Warning! Hit {hit.getObjectID().index} has a layer above 6 ({layer})!")
                        continue

                    if layer in excludes:
                        continue

                    if hit.getEnergy() > maxenes[layer]:
                        maxenes[layer] = hit.getEnergy()
                        maxhits[layer] = hit

            if cluster is None or len(maxhits) == 0:
                continue

            # pick out most upstream layer from
            # most energetic hits
            minlayer = min(maxhits.keys())

            # scrape info from max hit in most
            # upstream layer
            hinfo = Info()
            hinfo.set_hit_info(coord, maxhits[minlayer])

            # calculate difference
            hdiff.Fill(hinfo.angle - pinfo.angle)

    # resolution calculation --------------------------------------------------

    # extract hist properties to initialize fit
    muhist  = hdiff.GetMean()
    rmshist = hdiff.GetRMS()
    inthist = hdiff.Integral()

    # set up a gaussian to extract main peak
    fdiff = ROOT.TF1("fAngRes", "gaus(0)", -0.2, 0.2)
    fdiff.SetParameters(
        inthist,
        muhist,
        rmshist
    )

    # fit histogram over nonzero bins
    ifirst   = hdiff.FindFirstBinAbove(0.0)
    ilast    = hdiff.FindLastBinAbove(0.0)
    first_lo = hdiff.GetBinLowEdge(ifirst)
    last_hi  = hdiff.GetBinLowEdge(ilast + 1)
    hdiff.Fit("fAngRes", "", "", first_lo, last_hi)

    # wrap up script ----------------------------------------------------------

    # save root objects
    with ROOT.TFile(opts.ofile, "recreate") as out:
        out.WriteObject(fdiff, "fAngRes")
        out.WriteObject(hdiff, "hAngRes")
        out.Close()

    # save metrics to a json file
    metrics = {f"{opts.angle}_resolution" : fdiff.GetParameter(2)}
    js_out  = opts.ofile.replace(".root", ".json")
    with open(js_out, 'w') as o:
       json.dump(metrics, o)

    # and return fit width as resolution
    return {f"{opts.angle}_resolution" : fdiff.GetParameter(2)}

# =============================================================================
# Extract objective from an output file
# =============================================================================
def ExtractObjective(*, extra_args, **_):
    """Extract objective

       Extracts a metric based from the JSON file
       written by CalculateHitAngReso. The key
       of the value to extract and the path to
       the JSON file must be provided through
       the `extra_args` block.

       Args:
           extra_args: dictionary of extra arugments
                       must contain `key` and `file`
       Returns:
           extracted metric formatted as a dictionary
    """
    if 'key' not in extra_args:
        raise KeyError(f"'key' not found in extra_args! extra_args = {extra_args}")

    if 'file' not in extra_args:
        raise KeyError(f"'file' not found in extra_args! extra_args = {extra_args}")
    key  = extra_args['key']
    file = extra_args['file']

    metrics = {}
    with open(file, 'r') as f:
        data         = json.load(f)
        value        = data[key]
        metrics[key] = value
    return metrics

# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":

    # set up argments
    parser = ap.ArgumentParser()
    parser.add_argument(
        "-i",
        "--ifiles",
        help = "Add an input file",
        nargs = '?',
        action = 'append',
        type = str
    )
    parser.add_argument(
        "-o",
        "--ofile",
        help = "Output file",
        nargs = '?',
        const = DEFAULT_OPTS.ofile,
        default = DEFAULT_OPTS.ofile,
        type = str
    )
    parser.add_argument(
        "-c",
        "--angle",
        help = "Angular coordinate to calculate resolution on",
        nargs = '?',
        const = DEFAULT_OPTS.angle,
        default = DEFAULT_OPTS.angle,
        type = str
    )
    parser.add_argument(
        "-s",
        "--pdg",
        help = "PDG code of particle species to look for",
        nargs = '?',
        const = DEFAULT_OPTS.pdg,
        default = DEFAULT_OPTS.pdg,
        type = int
    )
    parser.add_argument(
        "-r",
        "--hits",
        help = "Reco hit collection to use",
        nargs = '?',
        const = DEFAULT_OPTS.hits,
        default = DEFAULT_OPTS.hits,
        type = str
    )
    parser.add_argument(
        "-p",
        "--pars",
        help = "MC particle collection to use",
        nargs = '?',
        const = DEFAULT_OPTS.pars,
        default = DEFAULT_OPTS.pars,
        type = str
    )
    parser.add_argument(
        "-a",
        "--assocs",
        help = "Cluster-particle associations to use",
        nargs = '?',
        const = DEFAULT_OPTS.assocs,
        default = DEFAULT_OPTS.assocs,
        type = str
    )
    parser.add_argument(
        "-e",
        "--excludes",
        help = "Add a layer to exclude",
        nargs = '?',
        action = 'append',
        type = int
    )

    # grab arguments
    args = parser.parse_args()

    # if no input files provided, use default one
    inputs = list()
    if args.ifiles is None:
        inputs.append(DEFAULT_OPTS.ifiles)
    else:
        inputs.extend(args.ifiles)

    # if no excluded layers provided, use default one
    excludes = list()
    if args.excludes is None:
        excludes.append(DEFAULT_OPTS.excludes)
    else:
        excludes.extend(args.excludes)

    # pack options and run analysis
    opts = Options(inputs, args.ofile, excludes)
    opts.set_opts_from_args(args)
    CalculateHitAngReso(opts)
