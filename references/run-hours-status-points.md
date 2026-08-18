# Run-hours status points

Status `metadata_id`s by equipment type for the `platform.favourites` call, in three tiers tried in order:

- `1_status` — a real status point. Always prefer these.
- `2_enable_command` — the enable or command point. Shows what was *commanded*, not what ran.
- `3_analog_proxy` — speed, load, amps or frequency. Treat a value above 5% of the observed max as ON.

Within a tier the first id listed for a type is the plain binary point; later ones are variants, and `(MSV)` rows are multi-state and carry the `{1,2}` ON convention rather than `{0,1}`.

tier	metadata_type	metadata_id	metadata_name	metadata_code
1_status	Chiller (CH)	9	Chiller Status	CH-St
1_status	Chiller (CH)	744	Chiller Status (MSV)	CH-St-MSV
1_status	Cooling Tower (CT)	15	Cooling Tower Fan Status	CT-FSt
1_status	Cooling Tower (CT)	1948	Cooling Tower Fan Status (MSV)	CT-F-Sts-MSV
1_status	Boiler (HWB)	19	Hot Water Boiler Status	HWB-ST
1_status	Boiler (HWB)	4889	Hot Water Boiler Status (MSV)	HWB-ST-MSV
1_status	Primary CHW Pumps (PCHWP)	32	Primary Chilled Water Pump Status	CHWP-St
1_status	Primary CHW Pumps (PCHWP)	1561	Primary Chilled Water Pump Flow Status	PCHWP-Flow-St
1_status	Primary CHW Pumps (PCHWP)	1935	Primary Chilled Water Pump Status (MSV)	PCHWP-St-MSV
1_status	Primary CHW Pumps (PCHWP)	2705	Primary Chilled Water Pump System Flow Status	PCHWP-Sys-Flow-Sts
1_status	Condenser Water Pumps (CWP)	37	Condenser Water Pump Status	CWPSt
1_status	Condenser Water Pumps (CWP)	1562	Condenser Water Pump Flow Status	CWP-Flow-St
1_status	Condenser Water Pumps (CWP)	1937	Condenser Water Pump Status (MSV)	CWP-St-MSV
1_status	Air Handling Units (AHU)	45	Unit Supply Air Fan Status	Un-SAF/St
1_status	Air Handling Units (AHU)	1133	Unit Duct Heater Status	Un-DH-St
1_status	Air Handling Units (AHU)	1917	Unit Supply Air Fan Status (MSV)	Un-SAF-St-MSV
1_status	Fan Coil Units Legacy (FCU)	66	FCU Fan Status	FCU-FSt
1_status	Fan Coil Units Legacy (FCU)	2279	FCU Fan Status (MSV)	FCU-SAF-Sts-MSV
1_status	Secondary CHW System (SCHW)	149	Secondary Chilled Water Pump Status	SCHWP-St
1_status	Secondary CHW System (SCHW)	1620	Secondary Chilled Water Pump Flow Status	SCHWP-F-St
1_status	Secondary CHW System (SCHW)	2624	Secondary Chilled Water System Flow Status	SCHWS-Flw-St
1_status	Domestic Hot Water (DHWT)	162	Domestic Hot Water Pump Status	DHWP-St
1_status	Packaged AC Units (PAC)	167	PAC Supply Air Fan Status	PAC-SAF-St
1_status	Packaged AC Units (PAC)	1004	PAC Compressor Status	PAC-CompSt
1_status	Packaged AC Units (PAC)	1141	PAC Return Air Fan Status	PAC-RAF-St
1_status	Packaged AC Units (PAC)	2185	PAC Supply Air Fan Status (MSV)	PAC-SAF-St-MSV
1_status	Primary HW Pumps (PHWP)	294	Primary Hot Water Pump Status	PHWP-St
1_status	Primary HW Pumps (PHWP)	1462	Primary Hot Water Pump Flow Status	PHWP-Flw-St
1_status	Primary HW Pumps (PHWP)	2706	Primary Hot Water Pump System Flow Status	PHWP-Sys-Flw-Sts
1_status	Secondary HW System (SHW)	300	Secondary Hot Water Pump Status	SHWP-St
1_status	Secondary HW System (SHW)	1467	Secondary Hot Water Pump Flow Status	SHWP-Flw-St
1_status	Secondary HW System (SHW)	2492	Secondary Hot Water Pump Status (MSV)	SHWP-St-MSV
1_status	Secondary HW System (SHW)	2625	Secondary Hot Water System Flow Status	SHWS-Flw-St
1_status	Calorifier (CAL)	1452	Calorifier Immersion Heater Status	CAL-IMM-St
1_status	Calorifier (CAL)	3841	Calorifier Domestic Hot Water Pump Status	CAL-DWHP-STS
1_status	Exhaust Air Fans (EAF)	591	Exhaust Air Fan Status	EF-St
1_status	Exhaust Air Fans (EAF)	1744	Exhaust Air Fan Flow Status	EAF-Fl-St
1_status	Car Park Ventilation (CPV)	762	Car Park Supply Air Fan Status	CP-SAF-St
1_status	Car Park Ventilation (CPV)	845	Car Park Exhaust Air Fan Status	CP-EAF-St
1_status	Supply Air Fan (SAF)	825	Supply Air Fan Status	SAF-St
1_status	Steam Boiler (SB)	853	Steam Boiler Status	SB-St
1_status	Light (LT)	868	Light Status	LT-St
1_status	Heat Recovery Unit (HRU)	1719	Heat Recovery Unit Fan Status	HRU-Fan-St
1_status	Heat Pump (HP)	931	Heat Pump Status	HP-St
1_status	Dry Cooler (DC)	1579	Dry Cooler Status	DC-St
1_status	Dry Cooler Primary Pump (DCP)	1593	Dry Cooler Primary Water Pump Status	DCP-St
1_status	Hydraulic Pump (HYD)	3448	Hydraulic Pump Status	HYD-St
2_enable_command	Chiller (CH)	170	Chiller Enable	CH-ENA
2_enable_command	Chiller (CH)	686	Master Cooling Call	MasterCOOLCALL
2_enable_command	Chiller (CH)	1947	Chiller Enable (MSV)	CH-Ena-MSV
2_enable_command	Chiller (CH)	3715	Master Cooling Call (MSV)	MasterCOOLCALL-MSV
2_enable_command	Cooling Tower (CT)	179	Cooling Tower Fan Enable	CTF-ENA
2_enable_command	Boiler (HWB)	183	Hot Water Boiler Enable	HWB-ENA
2_enable_command	Boiler (HWB)	2285	Master Heating Call	HWB-Mstr-Htg-Call
2_enable_command	Primary CHW Pumps (PCHWP)	101	Primary Chilled Water Pump Enable	CHWP-ENA
2_enable_command	Primary CHW Pumps (PCHWP)	1936	Primary Chilled Water Pump Enable (MSV)	PCHWP-Ena-MSV
2_enable_command	Condenser Water Pumps (CWP)	103	Condenser Water Pump Enable	CWP-ENA
2_enable_command	Air Handling Units (AHU)	110	Unit Supply Air Fan Enable	Un-SAF-ENA
2_enable_command	Air Handling Units (AHU)	339	Unit After Hours	Un-AH
2_enable_command	Air Handling Units (AHU)	371	Unit Occupancy	Un-Occ
2_enable_command	Air Handling Units (AHU)	709	Unit Duct Heater Enable	Un-DH-Ena
2_enable_command	Air Handling Units (AHU)	818	Unit Return Air Fan Enable	Un-RAF-ENA
2_enable_command	Air Handling Units (AHU)	969	Unit After Hours AC Mode	Un-AHAC-Mode
2_enable_command	Air Handling Units (AHU)	1736	Unit Operation Mode	Un-Op-Md
2_enable_command	Air Handling Units (AHU)	1918	Unit Supply Air Fan Enable (MSV)	Un-SAF-Ena-MSV
2_enable_command	Air Handling Units (AHU)	2412	Unit Occupancy (MSV)	Un-Occ-MSV
2_enable_command	Fan Coil Units Legacy (FCU)	391	FCU Supply Air Fan Enable	FCU-SAF-ENA
2_enable_command	Fan Coil Units Legacy (FCU)	392	FCU Occupancy	FCU-Occ
2_enable_command	Fan Coil Units Legacy (FCU)	533	FCU After Hours	FCU-AH
2_enable_command	Fan Coil Units Legacy (FCU)	757	FCU Electrical Duct Heater	FCU-EDH
2_enable_command	Secondary CHW System (SCHW)	148	Secondary Chilled Water Pump Enable	SCHWP-ENA
2_enable_command	Domestic Hot Water (DHWT)	161	Domestic Hot Water Pump Enable	DHWP-ENA
2_enable_command	Packaged AC Units (PAC)	166	PAC Supply Air Fan Enable	PAC-SAF-Ena
2_enable_command	Packaged AC Units (PAC)	168	PAC Compressor Enable	PAC-Comp-Ena
2_enable_command	Packaged AC Units (PAC)	1037	PAC Occupancy	PAC-Occ
2_enable_command	Packaged AC Units (PAC)	1082	PAC After Hours Enable	PAC-AH
2_enable_command	Packaged AC Units (PAC)	1142	PAC Return Air Fan Enable	PAC-RAF-Ena
2_enable_command	Packaged AC Units (PAC)	1185	PAC Cooling Call	PAC-CoolCall
2_enable_command	Packaged AC Units (PAC)	1457	PAC Operation Mode	PAC-Op-Md
2_enable_command	Packaged AC Units (PAC)	2206	PAC Occupancy (MSV)	PAC-Occ-MSV
2_enable_command	Packaged AC Units (PAC)	2494	PAC After Hours Enable (MSV)	PAC-AH-MSV
2_enable_command	Packaged AC Units (PAC)	3825	PAC Supply Air Fan Enable (MSV)	PAC-SAF-Ena-MSV
2_enable_command	Primary HW Pumps (PHWP)	293	Primary Hot Water Pump Enable	PHWP-ENA
2_enable_command	Secondary HW System (SHW)	299	Secondary Hot Water Pump Enable	SHWP-ENA
2_enable_command	Calorifier (CAL)	329	Calorifier Domestic Hot Water Pump Enable	CAL-DHWP-ENA
2_enable_command	Calorifier (CAL)	1464	Calorifier Heating Enable	CAL-Ht-Ena
2_enable_command	Calorifier (CAL)	4081	Calorifier Immersion Heater Enable	CAL-IMM-Ena
2_enable_command	Exhaust Air Fans (EAF)	589	Exhaust Air Fan Enable	EF-ENA
2_enable_command	Exhaust Air Fans (EAF)	2553	Exhaust Air Fan Enable (MSV)	EF-ENA-MSV
2_enable_command	Car Park Ventilation (CPV)	761	Car Park Supply Air Fan Enable	CP-SAF-ENA
2_enable_command	Car Park Ventilation (CPV)	844	Car Park Exhaust Air Fan Enable	CP-EAF-ENA
2_enable_command	Supply Air Fan (SAF)	824	Supply Air Fan Enable	SAF-ENA
2_enable_command	Steam Boiler (SB)	854	Steam Boiler Enable	SB-ENA
2_enable_command	Light (LT)	973	Light Enable	LT-Ena
2_enable_command	Heat Recovery Unit (HRU)	1718	Heat Recovery Unit Fan Enable	HRU-Fan-Ena
2_enable_command	Heat Pump (HP)	928	Heat Pump Enable	HP-Ena
2_enable_command	Dry Cooler (DC)	1061	Dry Cooler Enable	DC-Ena
2_enable_command	Dry Cooler Primary Pump (DCP)	1592	Dry Cooler Primary Water Pump Enable	DCP-Ena
2_enable_command	Hydraulic Pump (HYD)	3447	Hydraulic Pump Enable	HYD-Ena
2_enable_command	Unit Heater (UH)	4284	Unit Heater Fan Enable	UH-Ena
3_analog_proxy	Chiller (CH)	10	Cooling Load	CLOAD
3_analog_proxy	Chiller (CH)	12	Chiller Amperage	CHAmp
3_analog_proxy	Chiller (CH)	256	Chiller Load	CH-LOAD
3_analog_proxy	Chiller (CH)	896	Chiller Power Consumption	CH-Pow-Cons-kW
3_analog_proxy	Chiller (CH)	2382	Chiller VSD Frequency	CH-VSD-Hz
3_analog_proxy	Cooling Tower (CT)	16	Cooling Tower Fan Speed	CT-FS
3_analog_proxy	Primary CHW Pumps (PCHWP)	33	Primary Chilled Water Pump Speed	CHWP-Spd
3_analog_proxy	Condenser Water Pumps (CWP)	38	Condenser Water Pump Speed	CWPS
3_analog_proxy	Air Handling Units (AHU)	46	Unit Supply Air Fan Speed	Un-SAFS
3_analog_proxy	Air Handling Units (AHU)	2634	Unit Supply Air Velocity	Un-SAV
3_analog_proxy	Air Handling Units (AHU)	3171	Unit Supply Air Velocity (ft/min)	Un-SAV-ftmin
3_analog_proxy	Air Handling Units (AHU)	3240	Unit Supply Air Fan Amps	Un-SAF-Amps
3_analog_proxy	Fan Coil Units Legacy (FCU)	67	FCU Fan Speed	FCU-FS
3_analog_proxy	Secondary CHW System (SCHW)	152	Secondary Chilled Water Pump Speed	SCHWPS
3_analog_proxy	Packaged AC Units (PAC)	892	PAC Supply Air Fan Speed	PAC-SAFS
3_analog_proxy	Packaged AC Units (PAC)	1076	PAC Compressor Amperage	PAC-Comp-Amp
3_analog_proxy	Primary HW Pumps (PHWP)	620	Primary Hot Water Pump Speed	PHWPS
3_analog_proxy	Secondary HW System (SHW)	305	Secondary Hot Water Pump Speed	SHW-Pump-Spd
3_analog_proxy	Exhaust Air Fans (EAF)	590	Exhaust Air Fan Speed	EFS
3_analog_proxy	Exhaust Air Fans (EAF)	3109	Exhaust Air Fan Amperage	EF-Amp
3_analog_proxy	VSD (shared)	613	VSD Power	VSD-Pow
3_analog_proxy	VSD (shared)	615	VSD Operating Frequency	VSD-f
3_analog_proxy	VSD (shared)	616	VSD Current	VSD-Amp
3_analog_proxy	VSD (shared)	1183	VSD Speed %	VSD-S-Perc
3_analog_proxy	Car Park Ventilation (CPV)	763	Car Park Supply Air Fan Speed	CP-SAF-Spd
3_analog_proxy	Car Park Ventilation (CPV)	846	Car Park Exhaust Air Fan Speed	CP-EAF-Spd
3_analog_proxy	Supply Air Fan (SAF)	828	Supply Air Fan Speed	SAF-SPD
3_analog_proxy	Elevator (ELVTR)	2915	Elevator Direction Duration None	ELVTR-DIR-DUR-NONE
3_analog_proxy	Unit Heater (UH)	4933	Unit Heater Fan Output	UH-Fan-O
