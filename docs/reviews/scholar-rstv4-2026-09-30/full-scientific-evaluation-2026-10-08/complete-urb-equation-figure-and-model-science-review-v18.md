# URB-Solar_ An Open-Source Tool for Solar Power Prediction in Urban Areas：完整原文科学核验

全部6页、10图像项、3解析公式块、6组编号公式已直接审阅。原始表格计数未增加。

## Fig.1

- Entire flowchart: image→manual color rules→outline→K-means clustering→concave hull/alpha shape→2D footprint→extruded3D. Maximumsilhouette chooses cluster count, not independently measured building accuracy. Color/scale/height inputs remain manual; automated title does not mean fully automatic geometry.

## Fig.2

- Full onemap image and extracted same-color footprints; greenarrow visual illustration. No geographic scale/building-height data/ground-truth segmentation or error metric printed. Body later calls this final solid model though actualfigure is2D footprint; inherited figure reference error kept.

## Fig.3

- All tree workflow branches preserved: color trunk/crown→Delaunay triangulation/alpha shape→clustering→concave hull→2D→extrusion→3D components→combinedfulltree. Prose selects Delaunay instead ofconcavehull and revolution forillustration; diagramlabels extrusion vs captionextrusion/revolution and hybridbranches not unique executablealgorithm. No implementation inferred from arrows.

## Fig.4

- Photo, segmented2D trunk/crown,3Dtree allreviewed. CADmodel from singleimage requires scale/3Dassumptions, not measured 3Dspecies/opticaltransmission verification. Complete sourcefootnote nparks.gov.sg retained onfullpage, not new measuredleafdata.

## Fig.5

- Two3x3km/1x1km WRF domains, directredsolid/diffusebluedashed, timehour~7..18 and W/m²axis0..1000 reviewed. Caption0–24scale describes clock convention, not actualfull24hplottedrange. Finergrid sharp intermittentdrops notdemonstrated accuracy without measuredirradiance/errors. Prose10–12PM conflicts daytimeclock10..12; preserve originaltimewording, no nativefix.

## Fig.6

- Both geographic direct-radiation contours at2PM Singaporestandardtime24Aug2017, lat1.20/1.35/1.50, lon103.6..104.2, colorbar0..800ticks andblackboundary reviewed. Figurecontainsdirectonly; prose saysdirectanddiffuse shown6(b), no diffusemap or hiddendata invented. Two spatialresolutions differcloudfield, not independent observational skill validation.

## Fig.7

- Complete assignedmaterial CAD versus11AM radiationsurfacecontour, colorbar0/100/200/300/400W/m². Bodyassigns buildings.8/expressway.4/trees.1/flat-terrainWRF; these differ Fig9idealizedalbedos duedifferentcase, not numerical contradiction. Simulatedflux not PV electricalplantoutput; no area/moduleefficiency/IV/temperature/grid-loss conversion validated.

## Fig.8

- Both idealized24h clear/cloudy inputprofiles,red direct/bluedasheddiffuse, ownymax1000vs600 W/m². Completecloudcover label stillnonzero direct; modeldefinition notuniversalzero-direct assertion. Syntheticinputs notobservedvalidation; no unprintedtimepointvaluesdigitized.

## Fig.9

- Geometry andtopview allfourmaterials/tworaisedvoid-deckbuildingsA/B. Printedalbedos pavement.05/buildings.55/grass.25/trees.15 exactretained; no unspecifieddimensions/heights/opticalproperties invented.

## Fig.10

- Allfourtopviewpanels clearcoarse/clearfine/cloudycoarse/cloudyfine atabout11:30AM; fineboundarysharperqualitative, not quantitativeconvergenceorobservedradiometry. Clearcolorbarticks100/400/700/1000 versuscloudy300/425/550/675/800W/m² distinctscales cannotvisuallycomparecolorasameabsolutevalue. Exactunprintedfluxsamples notinvented.

## 1

- I directnormal W/m²,theta incidenceangle; projectedfluxneeds illuminatedface/shading/daytime convention toavoidnegativebackface values. No explicit clampinprintedline, actualfacealgorithmunknown. Generic studentsummaries not claimed completeboundarydefinition.

## 2–5

- Allfourphysicalnumberedexpressions retained includingM2minus. Forbeta0/thetaz45°/F.5, factor<1 versus horizontal input; printedline alonedoesnotreturninputDHIforhorizontalplane. UnderI=DHI=0, F0/0 undefined; no suppliednightbranch, not inferredactualcrash. InputsIdefinedDNI whilehorizontalGHIrelation/units/direct-vs-horizontal distinction need explicitnormalization. Originalauthorcode unavailable, no silently correctednamed-modelformula.

## 6

- Printedview-factor-basedclaim hasno explicitgeometricviewweightsorareas. Literalconditionaltwoequalfaces alpha=.5 andincidentS100 gives sumQ=-100+sumQ, impossible; actualsolvermayhavemissingweights/signconvention, not executedcodefailure. Negativeleadingabsorption maybesignconvention notbyitselfwrong. No fabricatedconservationtestforactualmesh.

## 方法与外推边界

- Fullproof-of-conceptboundary explicitconclusion: extensivefuturevalidationrequired. OneSingaporeToaPayoh1.334N103.856E withWRF23–24Aug2017chosenno-rain,firstdayspinupdiscarded; no independentmeasuredirradiance,forecastleadtime/skillbaseline/errors/uncertainty oryear-roundsampling.
- HistoricalWRF3.9/OpenFOAM5.0portedv1612 choices/NCEP-FNL forcings/5minradiation/48vertical10PBLlevels/fivephysicsoptions areauthorsreportedconfiguration, not validatedcurrentsoftwarefacts. Fourgrids27/9/3/1km andresolutionfigures donotbythemselvesverifyNWP accuracy.
- Bothmeshlinearresolutionsrefinedby8; surfacecellcountcouldscale64conditional2Darea, actualmeshcountsnotprovided. Less1minute64processors for6AM–6PM claimedsolarcalculatoronly, notmeasuredfullWRF/preprocessforecastlatency orhardwareindependentbenchmark.
- Buildingcolorbounds/type/scale/heightmanual; maximumsilhouette notsegmentationgold. Treeextrusion/revolution andalgebraictransmission noempiricalleaf/seasonalvalidation; nospecular/participatingmedium/currentactualsolverprovided.
- Forecastnumbers20%by2027 andcost4times2010–2017 remainhistoricalcitedclaims, not verifiedmodernfacts. RadiationW/m² differsPV powerW/kW; no demonstratedelectricalyieldmodel/comparator forurbanPVdeployment.
- Exactauthorrepositoryweb/metadataHTTP200 currentlyexistsbutsize0; actualcommitendpointHTTP409 Git Repository is empty. No current authorcodecommit toinspect/reproduce; doesnotproveoriginal2018code neverexisted. Failedtreehelperretainedbeforeanysourcefileswritten; no replacementrepositoryornewmodelinvented.

[完整原件、引用、算术和范围记录](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/complete-urb-equation-figure-and-model-science-review-v18.json)。
