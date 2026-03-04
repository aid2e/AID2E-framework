#include <random>
#include <vector>
#include <numeric>
#include <cmath>
#include "podio/ROOTFrameReader.h"
#include "podio/Frame.h"
#include "edm4eic/CherenkovParticleIDCollection.h"
#include "edm4hep/MCParticleCollection.h"
#include <chrono>
#include <TH1D.h>
#include <TF1.h>
#include <TCanvas.h>
#include <TError.h>

// struct to store needed data from each event,
// so that we only have to loop over tree once
struct EventData {
  std::vector<double> theta;      // theta*1000 per photon
  std::vector<double> thetaMC;      // thetaExpected*1000 per photon
  std::vector<double> thetaErr;   // |theta-expected| per photon
  double nPhotons;                   // number of photons
  bool   detected;                // nPhotons > 5
};

// loop over all events in the file, storing needed dRICH information
std::vector<EventData> readEventData(const char* infile, int radiator) {
  std::vector<EventData> events;
  podio::ROOTFrameReader reader;
  reader.openFile(infile);
  int nev = reader.getEntries("events");
  events.reserve(nev);
  
  // gas or aerogel radiator
  std::string pidCol;
  double n_refr;
  double thmin, thmax;
  if      (radiator==0){ pidCol="DRICHAerogelIrtCherenkovParticleID"; n_refr=1.019; thmax = 220; thmin = 150;  }
  else if (radiator==1){ pidCol="DRICHGasIrtCherenkovParticleID";    n_refr=1.00076; thmax = 50; thmin = 20;   }
  else throw std::runtime_error("bad radiator");
  
  for(int i=0;i<nev;++i) {
    auto frame = podio::Frame(reader.readNextEntry("events"));
    auto& chcol = frame.get<edm4eic::CherenkovParticleIDCollection>(pidCol);
    auto& mc    = frame.get<edm4hep::MCParticleCollection>("MCParticles");
    
    // get MC info, including expected cherenkov angle
    auto p4 = mc[0].getMomentum();
    double p = std::hypot(p4.x,p4.y,p4.z);
    double betaTrue = p/std::sqrt(p*p + mc[0].getMass()*mc[0].getMass());
    double chExpected = std::acos(1./(n_refr*betaTrue))*1000;
    
    // get data for event.
    // only keep reconstructed photons in a (wide) reasonable range
    for(const auto& pid : chcol) {
      EventData ed;
      ed.nPhotons = 0;//pid.getNpe();
      
      for(auto& tp : pid.getThetaPhiPhotons()) {
        double th = tp[0]*1000;
	if (th < thmax && th > thmin){
	  ed.theta    .push_back(th);
	  ed.thetaMC  .push_back(chExpected);
	  ed.thetaErr .push_back(th - chExpected);
	  ed.nPhotons+=1.;
	}
      }
      ed.detected = (ed.nPhotons>5); // for efficiency calculation
      events.push_back(std::move(ed));
    }
  }

  return events;
}

struct BootstrapResults {
  double mean_nPhot;
  double mean_theta;
  double mean_theta_mae;
  double frac_detected;
  double theta_error_sigma;
};

// bootstrap (sample with replacement) sampleSize events
// out of the vector of simulated dRICH events
BootstrapResults computeBootstrap(
    const std::vector<EventData>& events,
    int sampleSize,
    std::mt19937_64& rng,
    int doplots
    
) {
  std::uniform_int_distribution<> pick(0, events.size() - 1);


  double sum_nphot = 0.0;
  double sum_theta = 0.0;
  double sum_theta_err = 0.0;
  double total_photons = 0.0;
  int    n_detected = 0;

  // sample with replacement sampleSize times
  for (int i = 0; i < sampleSize; ++i) {
    const auto& ev = events[pick(rng)];
    sum_nphot += ev.nPhotons;
    if (ev.detected) ++n_detected;
    
    for (double th : ev.theta){    sum_theta     += th; total_photons += 1.;}
    for (double err : ev.thetaErr) {sum_theta_err += std::fabs(err);}
  }

  // for this set of sampled events, get information needed to
  // calculate metrics
  BootstrapResults out;
  out.mean_nPhot       = sum_nphot / sampleSize;
  out.frac_detected    = double(n_detected) / sampleSize;
  if (total_photons > 0) {
    out.mean_theta     = sum_theta     / total_photons;
    out.mean_theta_mae = sum_theta_err / total_photons;
  } else {
    //std::cout << "no photons detected " << std::endl;
    out.mean_theta     = 0.0;
    out.mean_theta_mae = 0.0;
  }
  return out;
}

std::tuple<double,double,double,double> bootstrapStats(const std::vector<EventData>& events_pi,
						       const std::vector<EventData>& events_K,
						       int sampleSize,
						       int nBootstrap
						       ){
  
  // compute piKsep and acceptance metrics nBoostrap times  
  std::vector<double> final_piKsep(nBootstrap), final_acc(nBootstrap);
  std::mt19937_64 rng(std::chrono::steady_clock::now().time_since_epoch().count());
  
  int doplots = 0;
  for(int b=0; b<nBootstrap; b++){
    if(b>0) doplots=0;

    // get MAE, nPhotons, etc from each resampling
    auto stats_pi = computeBootstrap(events_pi, sampleSize, rng, doplots);
    auto stats_K  = computeBootstrap(events_K,  sampleSize, rng, doplots);

    double cher_diff = std::fabs(stats_pi.mean_theta  - stats_K.mean_theta);

    double avg_mae = (stats_pi.mean_theta_mae + stats_K.mean_theta_mae)/2.;
    double avg_acc = (stats_pi.frac_detected + stats_K.frac_detected)/2.;
    double avg_nphot = (stats_pi.mean_nPhot + stats_K.mean_nPhot)/2.;    

    // calculate and store pion-kaon separation
    final_piKsep[b] = cher_diff*sqrt(avg_nphot)/avg_mae;
    final_acc[b] = avg_acc;
  }
  
  auto compute_stats = [&](const std::vector<double>& v){
    double N = v.size();
    double sum=std::accumulate(v.begin(), v.end(), 0.0);
    double mean = sum/N;
    double sq=0;
    for(double x : v) sq += (x-mean)*(x-mean);
    double stdev = std::sqrt(sq/(N-1));
    
    return std::tuple{mean, stdev};
  };
  
  // get mean and standard dev for acceptance and pi-K separation  
  auto [mean_acc, sd_acc] = compute_stats(final_acc);
  auto [mean_piKsep, sd_piKsep] = compute_stats(final_piKsep);

  return std::tuple{mean_acc, sd_acc, mean_piKsep, sd_piKsep};
}


void dRICHAna_boostrap(const char* infile_pi,
		       const char* infile_K,
		       const char* outname,
		       int radiator,
		       int sampleSize = 1000,
		       int nBootstrap = 100		       
		       )
{
  
  auto events_pi = readEventData(infile_pi, radiator);
  auto events_K  = readEventData(infile_K,  radiator);
  
  std::cout << "N ev pi: " << events_pi.size() << " K: " << events_K.size() << std::endl;
  if(sampleSize > events_pi.size()){
    sampleSize = events_pi.size();
  }
  if(sampleSize > events_K.size()){
    sampleSize = events_K.size();
  }
  
  auto [mean_acc, sd_acc, mean_piKsep, sd_piKsep]  = bootstrapStats(events_pi,                                       
								    events_K,
								    sampleSize,
								    nBootstrap
								    );
  if(sampleSize < events_pi.size()){    
    double ratio = double(sampleSize)/events_pi.size();    
    sd_piKsep *= ratio;
    sd_acc *= ratio;
  }
  
  FILE *outfile = fopen(outname,"w");
  fprintf(outfile, "%lf %lf %lf %lf \n", mean_acc, sd_acc, mean_piKsep, sd_piKsep);
  return;
}

int main(int argc, char* argv[]){
  if(argc < 7){
    std::cout << "usage: dRICHAana_boostrap [file, pi] [file, K] [output file name] [radiator: 0 - aerogel, 1 - gas] [N samples (optional)] [N boostraps] \n";
    return 1;
  }
  
  int rad         = std::stoi(argv[4]);
  int nsamples    = std::stoi(argv[5]);
  int nbootstraps = std::stoi(argv[6]);

  dRICHAna_boostrap(argv[1], argv[2], argv[3], rad, nsamples, nbootstraps);
  return 0;
}
