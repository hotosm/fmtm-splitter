 /*
Licence: GPLv3 <https://www.gnu.org/licenses/gpl-3.0.html>
Part of the HOT Field Mapping Tasking Manager (FMTM)

This script deletes the temporary PostGIS layers (tables) created by the previous four scripts, leaving only the clusteredbuildings and taskpolygons layers intact.

Obviously for development or research purposes where you want to inspect intermediate results, either don't run this script or comment out the relevant DROP statements.
*/

DROP TABLE IF EXISTS polygonsnocount;
DROP TABLE IF EXISTS buildings;
DROP TABLE IF EXISTS splitpolygons;
DROP TABLE IF EXISTS lowfeaturecountpolygons;
-- DROP TABLE IF EXISTS clusteredbuildings;
DROP TABLE IF EXISTS dumpedpoints;
DROP TABLE IF EXISTS voronoids;
DROP TABLE IF EXISTS voronois;
DROP TABLE IF EXISTS unsimplifiedtaskpolygons;
-- DROP TABLE IF EXISTS taskpolygons;
