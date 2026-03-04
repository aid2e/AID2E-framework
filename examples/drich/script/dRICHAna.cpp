#include "edm4hep/MCParticleCollection.h"
#include "edm4eic/CherenkovParticleIDCollection.h"
#include "podio/ROOTFrameReader.h"
#include "podio/Frame.h"
#include "TH1F.h"
#include "TF1.h"
#include "TCanvas.h"
#include "TString.h"
using namespace std;


void extractSPEres(const char* filename, const char* outname, const char* outdir, int radiator){

  double thlow, thhigh;
  int nbins;
  if(radiator==0){
    thlow = 150;
    thhigh = 220;
    nbins = 200;
  }
  else{
    thlow = 20;
    thhigh = 60;
    nbins = 100;
  }
  
  TH1F* hSingleThetaError = new TH1F("hSingleThetaError", "", 100, -10, 10);
  TH1F* hSingleTheta = new TH1F("hSingleTheta", "", nbins, thlow, thhigh);
  TH1F* hnPhotons = new TH1F("hnPhotons", "", 60, -0.5, 60.5);  
  
  podio::ROOTFrameReader reader;
  reader.openFile(filename);
  
  int nev = reader.getEntries("events");
  double nThrown = 0;
  double ndRICHDet = 0;    
  // event loop
  for(int i = 0; i < nev; i++){
    const auto event = podio::Frame(reader.readNextEntry("events"));

    std::string pidCollection;
    double n;
    if(radiator==0){
      pidCollection = "DRICHAerogelIrtCherenkovParticleID";
      n = 1.019;
    }
    else{
      pidCollection = "DRICHGasIrtCherenkovParticleID";
      n = 1.00076;
    }
    
    auto& dRichCherenkov = event.get<edm4eic::CherenkovParticleIDCollection>(pidCollection);
    auto& MCParticles = event.get<edm4hep::MCParticleCollection>("MCParticles");    

    double px, py, pz, p, mass;
    double betaTrue;
    // get true momentum from thrown particle
    if(MCParticles.isValid()){
      px = MCParticles[0].getMomentum().x;
      py = MCParticles[0].getMomentum().y;
      pz = MCParticles[0].getMomentum().z;
      p = sqrt(px*px+py*py+pz*pz);
      mass = MCParticles[0].getMass();
      betaTrue = p/(sqrt(p*p+mass*mass)); 
    }
    else{
      cout << "Error: no thrown particles" << endl;
      continue;
    }
    
    nThrown += 1.;
    if (dRichCherenkov.isValid()) {
      double chExpected = acos(1/(n*betaTrue))*1000;

      for(unsigned int j = 0; j < dRichCherenkov.size(); j++){
	auto thetaPhi = dRichCherenkov[j].getThetaPhiPhotons();

	int nPhotons = dRichCherenkov[j].getNpe();
	if(nPhotons == 0){
	  // if no photons, consider this to be missed
	  continue;
	}
	if(nPhotons > 5){
	  ndRICHDet += 1.; // if > 5 photons, consider this to be accepted
	}
	
	hnPhotons->Fill(nPhotons);	
	for(int k = 0; k < thetaPhi.size(); k++){
	  hSingleThetaError->Fill(abs(thetaPhi[k][0]*1000 - chExpected));
	  hSingleTheta->Fill(thetaPhi[k][0]*1000);
	}
      }      
    }       
  }

  //double mean = hSingleThetaError->GetMean();
  //double rms = hSingleThetaError->GetRMS();
  
  //TF1 *f1 = new TF1("gaussianFit", "gaus", mean-2*rms, mean+2*rms);  
  //hSingleThetaError->Fit("gaussianFit","R");

  TString outname_wdir = TString(outdir) + TString(outname);
  FILE *outfile = fopen(outname_wdir.Data(),"w");

  
  fprintf(outfile, "%lf %lf %lf %lf \n",
	  hnPhotons->GetMean(), hSingleTheta->GetMean(),
	  hSingleThetaError->GetMean(), // MAE
	  //f1->GetParameter(2),
	  ndRICHDet/nThrown);
  
  return;
}


int main(int argc, char* argv[]){
  if(argc < 2){
    cout << "usage: dRICHAana [filename] [outputname (txt)] [output dir] [radiator: 0 - aerogel, 1 - gas] \n";
    return 1;
  }
  int rad;
  stringstream s(argv[4]);
  s >> rad;
  
  extractSPEres(argv[1], argv[2], argv[3], rad);  
  return 0;  
}
