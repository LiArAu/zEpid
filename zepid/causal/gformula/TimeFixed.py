import warnings
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.genmod.families import links


class TimeFixedGFormula:
    def __init__(self, df, exposure, outcome, outcome_type='binary', weights=None):
        """Time-fixed implementation of the g-formula, also referred to as the g-computation algorithm formula. This
        implementation has three options for the treatment courses:

        Currently, only supports binary or continuous outcomes. For binary outcomes a logistic regression
        model to predict probabilities of outcomes via statsmodels. For continuous outcomes a linear regression
        model is used to predict outcomes.
        Binary and multivariate exposures are supported. For binary exposures, a string object of the column name for
        the exposure of interest should be provided. For multivariate exposures, a list of string objects corresponding
        to disjoint indicator terms for the exposure should be provided. Multivariate exposures require the user to
        custom specify treatments when fitting the g-formula. A list of the custom treatment must be provided and be
        the same length as the number of disjoint indicator columns. See
        http://zepid.readthedocs.io/en/latest/ for examples (highly recommended)

        Key options for treatments
            all     -all individuals are given treatment
            none    -no individuals are given treatment
            custom treatments
                    -create a custom treatment. When specifying this, the dataframe must be referred to as 'g' The
                    following is an example that selects those whose age is 30 or younger and are females;
                    treatment="((g['age0']<=30) & (g['male']==0))

        Parameters
        ----------
        df : DataFrame
            Pandas dataframe containing the variables of interest
        exposure : str, list
            Column name for exposure variable label or a list of disjoint indicator exposures
        outcome : str
            Column name for outcome variable
        outcome_type : str, optional
            Outcome variable type. Currently only 'binary' or 'continuous' variable types are supported
        weights : str, optional
            Column name for weights. Default is None, which assumes every observations has the same weight (i.e. 1)

        Examples
        --------
        >>>import zepid as ze
        >>>from zepid.causal.gformula import TimeFixedGFormula
        >>>df = ze.load_sample_data(timevary=False)
        >>>df[['cd4_rs1', 'cd4_rs2']] = ze.spline(df, 'cd40', n_knots=3, term=2, restricted=True)
        >>>df[['age_rs1', 'age_rs2']] = ze.spline(df, 'age0', n_knots=3, term=2, restricted=True)
        >>>g = TimeFixedGFormula(df, exposure='art', outcome='dead')
        >>>g.outcome_model(model='art + male + age0 + age_rs1 + age_rs2 + cd40 + cd4_rs1 + cd4_rs2 + dvl0')
        >>>g.fit(treatment='all')
        >>>print(g.marginal_outcome)

        References
        ----------
        Snowden, Jonathan M., Sherri Rose, and Kathleen M. Mortimer. "Implementation of G-computation on a simulated
        data set: demonstration of a causal inference technique." American Journal of Epidemiology 173.7 (2011):
        731-738.
        """
        self.gf = df.copy()
        self.exposure = exposure
        self.outcome = outcome
        if (outcome_type == 'binary') or (outcome_type == 'continuous'):
            self.outcome_type = outcome_type
        else:
            raise ValueError('Only binary or continuous outcomes are currently supported. Please specify "binary" or '
                             '"continuous"')
        self._weights = weights
        self.model_fit = False

    def outcome_model(self, model, print_results=True):
        """Build the model for the outcome. This is also referred to at the Q-model. This must be specified
        before the fit function. If it is not, an error will be raised.

        Parameters
        ----------
        model : str
            Variables to include in the model for predicting the outcome. Must be contained within the input
            pandas dataframe when initialized. Model form should contain the exposure, i.e. 'art + age + male'
        print_results : bool, optional
            Whether to print the logistic regression results to the terminal. Default is True
        """
        if self.outcome_type == 'binary':
            linkdist = sm.families.family.Binomial(sm.families.links.logit)
        else:
            linkdist = sm.families.family.Gaussian(sm.families.links.identity)

        # Modeling the outcome
        if self._weights is None:
            m = smf.glm(self.outcome+' ~ '+model, self.gf, family=linkdist)
            self.outcome_model = m.fit()
        else:
            m = smf.gee(self.outcome+' ~ '+model, self.gf.index, self.gf, family=linkdist,
                        weights=self.gf[self._weights])
            self.outcome_model = m.fit()

        # Printing results of the model and if any observations were dropped
        if print_results is True:
            print(self.outcome_model.summary())
        self.model_fit = True

    def fit(self, treatment):
        """Fit the parametric g-formula as specified. Binary and multivariate treatments are available. This
        implementation has three options for the binary treatment courses. For multivariate treatments, the user must
        specify custom treatment plans.

        To obtain the confidence intervals, use a bootstrap. See online documentation for an example:
        http://zepid.readthedocs.io/en/latest/

        Parameters
        ----------
        treatment : str, list
            There are three options available for treatment plans. All, none, or a custom pattern
            * all     -all individuals are given treatment
            * none    -no individuals are given treatment
            * custom  -create a custom treatment. When specifying this, the dataframe must be referred to as 'g' The
              following is an example that selects those whose age is 25 or older and are females;
              treatment="((g['age0']>=25) & (g['male']==0))

        Returns
        -------
        marginal_outcome
            Parameter of marginal outcome is filled, which is the mean predicted Y under the treatment strategy
        """
        if self.model_fit is False:
            raise ValueError('Before the g-formula can be calculated, the outcome model must be specified')
        if (type(treatment) != str) and (type(treatment) != list):
            raise ValueError('Specified treatment must be a string object or a list of string objects')

        # Setting outcome as blank
        g = self.gf.copy()

        # Setting treatment (either multivariate or binary)
        if type(self.exposure) == list:  # Multivariate exposure
            if (treatment == 'all') or (treatment == 'none'):  # Check to make sure custom treatment
                raise ValueError('A multivariate exposure has been specified. A custom treatment must be '
                                 'specified by the user')
            else:
                if len(self.exposure) != len(treatment):  # Check to make sure same about of treatments specified
                    raise ValueError('The list of custom treatment conditions must be the same size as the number of '
                                     'treatments')
                for i in range(len(self.exposure)):
                    g[self.exposure[i]] = np.where(eval(treatment[i]),1,0)
                if np.sum(np.where(g[self.exposure].sum(axis=1) > 1, 1, 0)) > 1:
                    warnings.warn('It looks like your specified treatment strategy results in some individuals '
                                  'receiving at least two exposures. Reconsider how the custom treatments are '
                                  'specified')

        else:  # Binary exposure
            if type(treatment) == list:
                raise ValueError('A binary exposure is specified. Treatment plan should be a string object')
            if treatment == 'all':
                g[self.exposure] = 1
            elif treatment == 'none':
                g[self.exposure] = 0
            else:  # custom exposure pattern
                g[self.exposure] = np.where(eval(treatment), 1, 0)

        # Getting predictions
        g[self.outcome] = np.nan
        g[self.outcome] = self.outcome_model.predict(g)
        if self._weights is None:  # unweighted marginal estimate
            self.marginal_outcome = np.mean(g[self.outcome])
        else:  # weighted marginal estimate
            self.marginal_outcome = np.average(g[self.outcome], weights=self.gf[self._weights])
        self.predicted_df = g
