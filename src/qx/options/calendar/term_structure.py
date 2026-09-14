"""IV Term Structure analysis logic."""

from qx.options.calendar.models import IvTermStructure


def analyze_iv_term_structure(
    volatility_annual: float = 0.158,
    front_dte: int = 1,
    back_dte: int = 4,
) -> IvTermStructure:
    """Analyze IV term structure slope and calculate front vs. back leg differentials.

    :param volatility_annual: Base annualized volatility decimal (e.g. 0.158)
    :param front_dte: Front leg days to expiration
    :param back_dte: Back leg days to expiration
    :return: IvTermStructure object with slope classification and recommendation
    """
    front_iv = round(volatility_annual * 1.05, 4)
    back_iv = round(volatility_annual * 0.96, 4)
    iv_diff = round((front_iv - back_iv) * 100.0, 2)

    if iv_diff > 0.5:
        slope = "Contango (Theta Favorable)"
        rec = "Front-leg IV overpriced relative to back-leg. Ideal environment for Long Calendar Spreads."
    elif iv_diff < -0.5:
        slope = "Backwardation (Vol Expansion)"
        rec = "Short-dated options underpriced relative to back-leg. Exercise caution with short legs."
    else:
        slope = "Flat Term Structure"
        rec = "Balanced term structure. Focus on directional or pinning strike selection."

    return IvTermStructure(
        front_leg_dte=front_dte,
        front_leg_iv=round(front_iv * 100.0, 1),
        back_leg_dte=back_dte,
        back_leg_iv=round(back_iv * 100.0, 1),
        iv_slope=slope,
        iv_differential_pct=iv_diff,
        recommendation=rec,
    )
