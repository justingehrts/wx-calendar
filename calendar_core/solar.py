"""Sunrise/sunset from the NOAA Global Monitoring Laboratory solar calculator algorithm (Meeus-based,
two-pass), the same method behind NOAA's web calculator. Standard refraction and solar radius: the Sun's
upper limb on the horizon (zenith 90.8333 degrees)."""
import math

rad, deg = math.radians, math.degrees
ZENITH = 90.8333      # 90 deg + 34' refraction + 16' solar radius

def julian_day(date):
    """Julian day at 0h UT of a calendar date."""
    y, m, d = date.year, date.month, date.day
    if m <= 2: y -= 1; m += 12
    a = y // 100; b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5

def _declination_and_equation_of_time(t):
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = (math.sin(rad(m)) * (1.914602 - t * (0.004817 + 0.000014 * t)) + math.sin(rad(2 * m)) * (0.019993 - 0.000101 * t)
         + math.sin(rad(3 * m)) * 0.000289)
    omega = 125.04 - 1934.136 * t
    apparent_long = l0 + c - 0.00569 - 0.00478 * math.sin(rad(omega))
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * math.cos(rad(omega))
    decl = deg(math.asin(math.sin(rad(eps)) * math.sin(rad(apparent_long))))
    y = math.tan(rad(eps / 2)) ** 2
    eqt = 4 * deg(y * math.sin(2 * rad(l0)) - 2 * e * math.sin(rad(m)) + 4 * e * y * math.sin(rad(m)) * math.cos(2 * rad(l0))
                  - 0.5 * y * y * math.sin(4 * rad(l0)) - 1.25 * e * e * math.sin(2 * rad(m)))
    return decl, eqt

def _event_utc_minutes(rise, jd, lat, lon_east):
    decl, eqt = _declination_and_equation_of_time((jd - 2451545.0) / 36525.0)
    cos_ha = math.cos(rad(ZENITH)) / (math.cos(rad(lat)) * math.cos(rad(decl))) - math.tan(rad(lat)) * math.tan(rad(decl))
    ha = math.acos(max(-1.0, min(1.0, cos_ha)))          # polar day/night would need special handling; not relevant at 40 N
    return 720 - 4 * (lon_east + (deg(ha) if rise else -deg(ha))) - eqt

def event_utc_minutes(date, lat, lon_east, rise):
    """Minutes after 0h UT on `date` at which the Sun rises (or sets). First estimate near local noon,
    then re-evaluated at that time, as NOAA's calculator does."""
    jd = julian_day(date)
    first = _event_utc_minutes(rise, jd + 0.5 + lon_east / 360.0, lat, lon_east)
    return _event_utc_minutes(rise, jd + first / 1440.0, lat, lon_east)
