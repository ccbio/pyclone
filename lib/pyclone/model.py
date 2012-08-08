'''
Created on 2011-12-29

@author: Andrew Roth
'''
from __future__ import division

from collections import OrderedDict
from math import lgamma as log_gamma, log, exp

from pyclone.utils import log_sum_exp, log_binomial_coefficient, log_binomial_likelihood, log_beta_pdf

class DataPoint(object):
    def __init__(self, a, d, mu_r, mu_v, delta_r, delta_v):
        self.a = a
        self.d = d
               
        self.mu_r = mu_r
        self.mu_v = mu_v
        
        self.delta_r = delta_r
        self.delta_v = delta_v        

#=======================================================================================================================
# Likelihood
#=======================================================================================================================
class Likelihood(object):
    def __init__(self, data_point):
        self.a = data_point.a
        self.d = data_point.d        
        
        self.log_pi_r = self._get_log_mix_weights(data_point.delta_r)
        self.log_pi_v = self._get_log_mix_weights(data_point.delta_v) 
        
        self._log_binomial_norm_const = log_binomial_coefficient(self.d, self.a)
        
        self._ll_cache = OrderedDict()
        
    def compute_log_likelihood(self, phi):        
        if phi not in self._ll_cache:
            self._ll_cache[phi] = self._log_likelihood(phi)
            
            if len(self._ll_cache) > 1000:
                self._ll_cache.popitem(last=False)
        
        return self._ll_cache[phi]

    def _log_likelihood(self, phi):
        '''
        Must be implemented by subclasses. Should return the log likelihood given the cellular frequency phi.
        '''
        raise NotImplemented    

    def _get_log_mix_weights(self, delta):
        log_denominator = log_gamma(sum(delta) + 1)
        
        log_mix_weights = []
        
        for i, d_i in enumerate(delta):
            log_numerator = log_gamma(d_i + 1)
            
            for j, d_j in enumerate(delta):
                if i != j:
                    log_numerator += log_gamma(d_j)
            
            log_mix_weights.append(log_numerator - log_denominator)
        
        return log_mix_weights        

    def _log_binomial_likelihood(self, phi, mu_r, mu_v):
        mu = (1 - phi) * mu_r + phi * mu_v
        
        return self._log_binomial_norm_const + log_binomial_likelihood(self.a, self.d, mu)
    
class BinomialLikelihood(Likelihood):
    def __init__(self, data_point):
        Likelihood.__init__(self, data_point)
        
        self.mu_r = data_point.mu_r
        self.mu_v = data_point.mu_v

    def _log_likelihood(self, phi):  
        ll = []
        
        for mu_r, log_pi_r in zip(self.mu_r, self.log_pi_r):
            for mu_v, log_pi_v in zip(self.mu_v, self.log_pi_v):
                temp = log_pi_r + log_pi_v + self._log_binomial_likelihood(phi, mu_r, mu_v)
                
                ll.append(temp)
        
        return log_sum_exp(ll)

class BetaBinomialLikelihood(Likelihood):
    def __init__(self, data_point, mesh_size=100, beta_precision=100):
        '''
        Likelihood with a beta prior over mu_v. 
        
        Kwargs:
            mesh_size : (int) Number of bins to use for numerical integration.
            beta_precision : (float) This is equal to alpha + beta. Higher values lead to more tightly peaked priors.
        ''' 
        Likelihood.__init__(self, data_point)
        
        self.mu_r = data_point.mu_r
                
        self._set_beta_params(data_point.mu_v, beta_precision)
        
        self._set_mesh(mesh_size)

    def _log_likelihood(self, phi):    
        ll = []
        
        for mu_r, log_pi_r in zip(self.mu_r, self.log_pi_r):
            for alpha_v, beta_v, log_pi_v in zip(self.alpha_v, self.beta_v, self.log_pi_v):
                temp = log_pi_r + log_pi_v + self._log_beta_binomial_likelihood(phi, mu_r, alpha_v, beta_v)
                
                ll.append(temp)
        
        return log_sum_exp(ll)

    def _log_beta_binomial_likelihood(self, phi, mu_r, alpha_v, beta_v):
        '''
        Log likelihood obtained by integrating out mu_v against a beta prior.
        '''
        log_sum = []
            
        for mu_v in self._mesh:
            y_i = self._log_binomial_likelihood(phi, mu_r, mu_v) + log_beta_pdf(mu_v, alpha_v, beta_v)
    
            log_sum.append(y_i + self._log_xi)
                
        return log_sum_exp(log_sum)
    
    def _set_beta_params(self, mu_v, s):
        self.alpha_v = []
        self.beta_v = []
        
        for m in mu_v:
            alpha = s * m
            beta = s - alpha
            
            self.alpha_v.append(alpha)
            self.beta_v.append(beta)
    
    def _set_mesh(self, mesh_size):
        '''
        Setup mesh for mid-point integration.
        '''
        knots = [i / mesh_size for i in range(0, mesh_size + 1)]
        
        # Bin centers for integration
        self._mesh = [(knots[i] + knots[i + 1]) / 2 for i in range(0, mesh_size)]
        
        # Log of delta x value for Riemann sum
        self._log_xi = -log(mesh_size)
        
def get_independent_posterior(data_point, num_bins):
    likelihood = BinomialLikelihood(data_point)
    
    bin_width = 1 / num_bins
    
    num_endpoints = num_bins + 1
    
    endpoints = [(x * bin_width) for x in range(num_endpoints)]
    
    bin_centres = []
    
    for left, right in zip(endpoints[:-1], endpoints[1:]):
        bin_centres.append((left + right) / 2)
    
    ll = []
    
    for phi in bin_centres:
        ll.append(likelihood.compute_log_likelihood(phi))
    
    norm_const = log_sum_exp([x + log(bin_width) for x in ll])
    
    pdf = [exp(x - norm_const) for x in ll]
    
    return zip(bin_centres, pdf) 