import sys
from datetime import date, timedelta
from StringIO import StringIO
from copy import copy
import psycopg2
import codecs
import zipfile
import fileinput
from bitstring import Bits

charset = 'iso-8859-1'

out = codecs.getwriter('utf-8')(sys.stdout)

def parse_day(day):
    day = day.split('.')
    return date(int(day[2]), int(day[1]), int(day[0]))

def simple_list_writer(conn,filename, arguments, data):
    f = StringIO()
    f.write('\t'.join(arguments) + '\n')
    for y in data:
        f.write('\t'.join([unicode(y[z] or '') for z in arguments]) + '\n')
    f.seek(0)
    cur = conn.cursor()
    cur.copy_expert("COPY %s FROM STDIN USING DELIMITERS '	' CSV HEADER NULL AS ''" % (filename),f)
    cur.close()
    f.close()

def simple_dict_writer(conn,filename, arguments, data):
    f = StringIO()
    f.write('\t'.join(arguments) + '\n')
    for x, y in data.items():
        f.write('\t'.join([unicode(x)] + [unicode(y[z] or '') for z in arguments[1:]]) + '\n')
    f.seek(0)
    cur = conn.cursor()
    cur.copy_expert("COPY %s FROM STDIN USING DELIMITERS '	' CSV HEADER NULL AS ''" % (filename),f)
    cur.close()
    f.close()

def simple_dict_list_writer(conn,filename, arguments, data):
    f = StringIO()
    f.write('\t'.join(arguments) + '\n')
    for x, y in data.items():
        for u in y:
            f.write('\t'.join([unicode(x)] + [unicode(u[z] or '') for z in arguments[1:]]) + '\n')
    f.seek(0)
    cur = conn.cursor()
    cur.copy_expert("COPY %s FROM STDIN USING DELIMITERS '	' CSV HEADER NULL AS ''" % (filename),f)
    cur.close()
    f.close()

def parse_bahnhof(zip,filename):
	# key:Haltestellennummer
	# Haltestellennummer: first two digits are the UIC Countrycode. In Switzerland (85) the Station are managed by the http://www.bav.admin.ch/dokumentation/publikationen/00475/01497/index.html?lang=de . For any changes there is a form on the website. In Switzerland the longname could only be 30 digits. 
    bahnhofen = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        haltestellennummer = line[:7].strip()
        haltestellenname = line[12:].split('$<')
        name = haltestellenname[0]
        longname = None
        abkurzung = None
        synonym = None
        for x in haltestellenname[1:]:
            if x[:2] == '1>':
                longname = x[3:]
            elif x[:2] == '2>':
                abkurzung = x[3:]
            elif x[:2] == '3>':
                synonym = x[3:]
        bahnhofen.append({'haltestellennummer' : haltestellennummer,
                          'longname'  : longname,
                          'abkurzung' : abkurzung,
                          'name' : name,
                          'synonym' : synonym})
    return bahnhofen

def parse_bfkoord(zip,filename):
	# key: Haltestellennummer
	# x,y in CH1903 format
    bfkoord = []
    for line in fileinput.input([filename], openhook=zip.open):
        haltestellennummer = line[:7].strip()
        x = line[8:18].strip()
        y = line[19:29].strip()
        z = line[30:36].strip()
        bfkoord.append({'haltestellennummer' : haltestellennummer,
                        'x'  : x,
                        'y' : y,
                        'z' : z})
    return bfkoord

def parse_fplan(zip,filename,conn):
	# key: fahrtnummer, verwaltung
    fplan = {}
    fplan['Z'] = [] # a new journey begins always with a z-row
    fplan['G'] = [] # which means of transport is used
    fplan['A_VE'] = [] # at which day of the week the journey is sheduled -- 00000000 means daily
    fplan['A'] = []  # attribute for a journey
    fplan['I'] = []  # freetext for a journey
    fplan['R'] = []  # information about the direction
    fplan['GR'] = [] # "station" which are important for the calculation of the price or the represent a frontier
    fplan['SH'] = [] # for seasonal operated stations
    fplan['L'] = []  # Information about the line (eg. bus, tramway, subway)
    fplan['LAUFWEG'] = []
    idx = 0

    primary = None

    for line in fileinput.input([filename], openhook=zip.open):

        line = line.decode(charset).replace('\r', '').replace('\n', '')
        # SBB has all keys already per line.
        kommentar = { 'fahrtnummer': line[60:65],
                      'verwaltung': line[66:72],
                      'variante': line[76:78],
                      'zeilennummer': line[80:83] }

        if line[:2] == '*Z':
            if len(fplan['Z']) == 1000:
                sql_fplan(conn,fplan)
                fplan = {}
                fplan['Z'] = []
                fplan['G'] = []
                fplan['A_VE'] = []
                fplan['A'] = []
                fplan['I'] = []
                fplan['R'] = []
                fplan['GR'] = []
                fplan['SH'] = []
                fplan['L'] = []
                fplan['LAUFWEG'] = []

            idx = idx + 1
            primary = { 'id': idx }

            item = { 'fahrtnummer': line[3:8].strip(),
                     'verwaltung': line[9:15].strip(),
                     'variante': line[18:21].strip(),
                     'taktanzahl': line[22:25].strip(),
                     'takzeit': line[26:29].strip() }
            item.update(primary)
            fplan['Z'].append(item)

        elif line[:2] == '*G':   # could be more than one for a journey the 'verkehrsmittel' is specified in ZUGART
            item = { 'verkehrsmittel': line[3:6].strip(),
                     'laufwegsindexab': line[7:14].strip(),
                     'laufwegsindexbis': line[15:22].strip(),
                     'indexab': line[23:29].strip(),
                     'indexbis': line[30:36].strip() }
            item.update(primary)
            fplan['G'].append(item)

        elif line[:5] == '*A VE':  # 00000000 means operated daily. other verkehrstagenummer are specified in BITFELD
            item = { 'laufwegsindexab': line[6:13].strip(),
                     'laufwegsindexbis': line[14:21].strip(),
                     'verkehrstagenummer': line[22:28].strip(),
                     'indexab': line[29:35].strip(),
                     'indexbis': line[36:42].strip() }
            item.update(primary)
            fplan['A_VE'].append(item)

        elif line[:2] == '*A': # attributes belonging to the journey, attribute codes are specified in ATTRIBUT_DE. The bitfeldnummer indicates that the attribut is not valid for every day  
            item = { 'attributscode': line[3:5].strip(),
                     'laufwegsindexab': line[6:13].strip(),
                     'laufwegsindexbis': line[14:21].strip(),
                     'bitfeldnummer': line[22:28].strip(),  # specified in BITFELD
                     'indexab': line[29:35].strip(),
                     'indexbis': line[36:42].strip() }
            item.update(primary)
            fplan['A'].append(item)

        elif line[:2] == '*I':  # freetext for the journey. The text is specified in INFOTEXT_DE. The bitfeldnummer indicates that the free text is not valid for every day.
            item = { 'infotextcode': line[3:5].strip(),
                     'laufwegsindexab': line[6:13].strip(),
                     'laufwegsindexbis': line[14:21].strip(),
                     'bitfeldnummer': line[22:28].strip(),
                     'infotextnummer': line[29:36].strip(),
                     'indexab': line[37:43].strip(),
                     'indexbis': line[44:50].strip() }
            item.update(primary)
            fplan['I'].append(item)

        elif line[:2] == '*L':  # Information about the line. 
            item = { 'liniennummer': line[3:11].strip(),
                     'laufwegsindexab': line[12:19].strip(),  #optional
                     'laufwegsindexbis': line[20:27].strip(), #optional
                     'indexab': line[28:34].strip(),
                     'indexbis': line[35:41].strip() }
            item.update(primary)
            fplan['L'].append(item)

        elif line[:2] == '*R':  # Which direction is marked on the mean of transportation
            item = { 'kennung': line[3:4].strip(),
                     'richtungscode': line[5:12].strip(),
					 # could be a station (BAHNHOF) or specified in RICHTUNG
                     'laufwegsindexab': line[13:20].strip(),
                     'laufwegsindexbis': line[21:28].strip(),
                     'indexab': line[29:35].strip(),
                     'indexbis': line[36:42].strip() }
            item.update(primary)
            fplan['R'].append(item)

        elif line[:3] == '*GR':  
            item = { 'grenzpunktnummer': line[4:11].strip(),
                     'laufwegsindexletzten': line[12:19].strip(),
                     'laufwegsindexersten': line[21:27].strip(),
                     'indexletzten': line[28:34].strip(),
                     'indexersten': line[35:41].strip() }
            item.update(primary)
            fplan['GR'].append(item)

        elif line[:3] == '*SH': # station which is not regularly operated. bitfeldnummer is specified in BITFELD
            item = { 'laufwegindex': line[4:11].strip(),
                     'bitfeldnummer': line[12:18].strip(),
                     'indexfur': line[19:25].strip() }
            item.update(primary)
            fplan['SH'].append(item)

        else:
            item = { 'haltestellennummer': line[:7].strip(),
                     'haltestellenname': line[8:29].strip(),
                     'ankunfstzeit': line[29:35].strip(), # if a journey last longer than midnigt. the time is runing further with 25 (~01 am) and so on
                     'abfahrtszeit': line[36:42].strip(), # if a journey last longer than midnigt. the time is runing further with 25 (~01 am) and so 
                     'fahrtnummer': line[43:48].strip(),
                     'verwaltung': line[49:55].strip(),
                     'x': line[56:57] }
            item.update(primary)
            fplan['LAUFWEG'].append(item)
    return fplan

def parse_dirwagen(zip,filename):
	# key: kurswagennummer
    kw = []
    kwz_zeilen = []
    a_ve_zeilen = []
    a_zeilen = []
    kurswagennummer = None
    idx = 0

    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        if line[:3] == '*KW':
            idx = idx + 1
            kurswagennummer = line[4:9]
            item = { 'id': idx,
                     'kurswagennummer': kurswagennummer }
            kw.append(item)

        elif line[:4] == '*KWZ':
            item = { 'id': idx,
                     'zugnummer': line[5:10],
                     'verhaltung': line[11:17],
                     'bahnhofsnummerab': line[18:25],
                     'bahnhofsname': line[26:46],
                     'bahnhofsnummerbis': line[47:54],
                     'abfahrtzeit1': line[76:82],
                     'abfahrtzeit2': line[83:89] }
            kwz_zeilen.append(item)

        elif line[:5] == '*A VE':
            item = { 'id': idx,
                     'laufwegindexab': line[6:13].strip(),
                     'laufwegindexbis': line[14:21].strip(),
                     'verkehrstagenummer': line[22:28].strip() }
            a_ve_zeilen.append(item)

        elif line[:2] == '*A':
            item = { 'id': idx,
                     'attributscode': line[3:5],
                     'laufwegsindexab': line[6:13],
                     'laufwegsindexbis': line[14:21] }
            a_zeilen.append(item)

        #item.update(kommentar)
    return kw,kwz_zeilen,a_ve_zeilen,a_zeilen

def parse_eckdaten(zip,filename):
    l_content = zip.read(filename).decode(charset).split('\r\n')[:-1]
    eckdaten = {}
    eckdaten['fahrplan_start'] = parse_day(l_content[0])
    eckdaten['fahrplan_end'] = parse_day(l_content[1])
    bezeichnung,fahrplan_periode,land,exportdatum,hrdf_version,lieferant = l_content[2].split('$')
    eckdaten['bezeichnung'] = bezeichnung
    eckdaten['fahrplan_periode'] = fahrplan_periode
    eckdaten['land'] = land
    eckdaten['exportdatum'] = exportdatum
    eckdaten['hrdf_version'] = hrdf_version
    eckdaten['lieferant'] = lieferant
    return eckdaten

def parse_bitfeld(zip,filename,eckdaten):
	# key: bitfeldnummer
	# The bit field consists of 380 bits (days). The first bit represents the beginning the timetable period. after the last bit at the end of the timetable period every bit is set to 0.
	# For the data compact each 4 bits are to a hexadecimal digit summarized.
    bitfelds = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        bitfeldnummer = line[:6]
        bitfeld = {'bitfeldnummer' : bitfeldnummer,'dates' : []}
        bitstring = str(Bits(hex=line[8:]).bin)
        for z in range(0, len(bitstring)):
            if bitstring[z] == '1':
                bitfeld['dates'].append(eckdaten['fahrplan_start']  + timedelta(days=z))
        bitfelds.append(bitfeld)
    return bitfelds


def parse_bfkoord_geo(zip,filename):
	# key: Haltestellennummer
	# coordinates in wgs84 format
    bfkoord_geo = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        haltestellennummer = int(line[:7].strip())
        x = line[8:18].strip()
        y = line[19:29].strip()
        z = line[30:36].strip()
        bfkoord_geo.append({'haltestellennummer' : haltestellennummer,
                            'x'  : x,
                            'y' : y,
                            'z' : z})
    return bfkoord_geo

def parse_umsteigb(zip,filename):
	# key: haltestellennummer
	# 9999999 is the default time for all transfers, which are not indicated specially
    umsteigb = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        umsteigb.append({'haltestellennummer' : line[:7],
                         'umsteigezeit_ic' : line[8:10],
                         'umsteigezeit' : line[11:13]})
    return umsteigb

def parse_bfprios(zip,filename):
	# key: Haltestellennummer
	# when there are different possabilities for a transfer between two journey. The station with the highest umsteigeprioritat is to use. 
	# Default is 8, min: Zero, max: 16
    bfprios = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')

        bfprios.append({'haltestellennummer' : line[:7],
                        'umsteigeprioritat' : line[8:10]})
    return bfprios

def parse_vereinig(zip,filename):
	# key: fahrtnummer1, fahrtnummer2, verwaltung1, verwaltung2
	# two trains are driving together (eg. lötschberger between bern-spiez, the the train is splitted (spiez-brig;spiez-zweisimmen)
    vereinig = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')

        vereinig.append({'haltestellennummer1' : line[:7],
                         'haltestellennummer2' : line[8:15],
                         'fahrtnummer1' : line[16:21],
                         'verwaltung1' : line[22:28],
                         'fahrtnummer2' : line[29:34],
                         'verwaltung2' : line[35:41],
                         'kommentar' : line[42:]})
    return vereinig

def parse_infotext(zip,filename):
	# key: infotextnummer
    infotext = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')

        infotext.append({'infotextnummer' : line[:8],
                         'informationstext' : line[8:]})
    return infotext

def parse_kminfo(zip,filename):
	# key: haltestellennummer
    kminfo = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')

        kminfo.append({'haltestellennummer' : line[:7],
                       'wert' : line[8:13]})   # 300000 transfer allowed, 0 transfer not allowed
    return kminfo

	
	# if there are more than one definition for the transfertimes the most specific one 'wins'. 	
def parse_umsteigv(zip,filename):
	# key: haltestellennummer, verwaltungsbezeichnung1, verwaltungsbezeichnung2
	# is used, when one of the transport agency only has one mean of transportation. Then it is usefull to give the transfertimes globaly for all journey. eg. 
    umsteigv = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')

        haltestellennummer = line[:7]
        if haltestellennummer == '@@@@@@@':  #the time is used for each station which is not specialy marked
            haltestellennummer = None
        umsteigv.append({'haltestellennummer' : haltestellennummer,
                         'verwaltungsbezeichnung1' : line[8:14],
                         'verwaltungsbezeichnung2' : line[15:21],
                         'mindestumsteigezeit' : line[22:24]})
    return umsteigv

def parse_umsteigl(zip,filename):
    # key: haltestellennummer, verwaltung1, verwaltung2, richtung1; richtung2, linie1, linie2
    # transfer dependend on direction. If there is a difference in transfertime between two means of transportation regarding the direcetion.

    umsteigl = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')

        haltestellennummer = line[:7]
        if haltestellennummer == '@@@@@@@': #the time is used for each station which is not specialy marked. @@@@@@ can be combined with the other parameters.
            haltestellennummer = None
        umsteigl.append({'haltestellennummer' : haltestellennummer,
                         'verwaltung1' : line[8:14],
                         'gattung1' : line[15:18],
                         'linie1' : line[19:27],
                         'richtung1' : line[28:29],
                         'verwaltung2' : line[30:36],
                         'gattung2' : line[37:40],
                         'linie2' : line[41:49],
                         'richtung2' : line[50:51],
                         'umsteigezeit' : line[52:55],
                         'garantiert' : line[55:56] == '!'})
    return umsteigl

def parse_umsteigz(zip,filename):
    # key: haltestellennummer, fahrtnummer1, verwaltung1; fahrtnummer2, verwaltung2
	# transfertimes between journey. 
	# if the time between the two trains is less than the transfertime, the transfer is not allowed (somekind strange way of blocking a transfer)
    umsteigz = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')b

        haltestellennummer = line[:7]
        if haltestellennummer == '@@@@@@@':
            haltestellennummer = None
        umsteigz.append({'haltestellennummer' : haltestellennummer,
                         'fahrtnummer1' : line[8:14],
                         'verwaltung1' : line[14:20],
                         'fahrtnummer2' : line[22:26],
                         'verwaltung2' : line[27:33],
                         'umsteigezeit' : line[34:37],
                         'garantiert' : line[37:38] == '!'})
    return umsteigz

def parse_gleis(zip,filename):
	# key: haltestellennummer, fahrtnummer, verwaltung, verkehrstageschlussel
    gleis = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        if line[0] == '%':
            continue #Nothing mentioned about this in docs??
        gleis.append({ 'haltestellennummer' : line[:7].strip(),
                       'fahrtnummer' : line[8:13].strip(),	
                       'verwaltung' : line[14:20].strip(),
                       'gleisinformation' : line[21:29].strip(),
                       'zeit' : line[30:34].strip(),  # is used when a mean of transportation passes the same station more than once in a journey
                       'verkehrstageschlussel' : line[35:41].strip()})
    return gleis

def parse_betrieb(zip,filename):
	# key: kurzname
    betrieb1 = []
    betrieb2 = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        if line[6] == ':':
            betrieb2.append({'betreibernummer' : line[:5],
                             'verwaltungen' : line[8:]})
        else:
            kurzname = []
            langname = []
            name = []
            i = 6
            k = False
            l = False
            v = False
            while i < len(line)-1:
                if line[i] == 'K':
                    k = True
                elif line[i] == 'L':
                    l = True
                elif line[i] == 'V':
                    v = True
                if line[i] == '"' and k:
                    k = False
                    i += 1
                    while i < len(line) and line[i] != '"':
                        kurzname.append(line[i])
                        i += 1
                if line[i] == '"' and l:
                    l = False
                    i += 1
                    while i < len(line) and line[i] != '"':
                        langname.append(line[i])
                        i += 1
                if line[i] == '"' and v:
                    v = False
                    i += 1
                    while i < len(line) and line[i] != '"':
                        name.append(line[i])
                        i += 1
                i += 1
            betrieb1.append({'betreibernummer' : line[:5],
                             'kurzname' : ''.join(kurzname).replace('\t',' '),
                             'langname' : ''.join(langname).replace('\t',' '),
                             'name' : ''.join(name).replace('\t',' ')})
    return betrieb1,betrieb2

def parse_attribut(zip,filename):
	# key: code
    attribut1 = []
    attribut2 = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        if line[0] == '#':
            attribut2.append({'code' : line[2:4],
                              'ausgabe_der_teilstrecke' : line[5:7], #Or wtf ever this means?/
                              'einstellig' : line[8:10]})
        else:
            attribut1.append({'code' : line[:2],
                              'haltestellenzugehorigkeit' : line[3:4],
                              'attributsausgabeprioritat' : line[5:8],
                              'attibutsausgabefeinsortierung' : line[9:11],
                              'text' : line[12:-1]})
    return attribut1,attribut2

def parse_richtung(zip,filename):
	# key: richtingschlussel
    richtung = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        richtung.append({'richtingschlussel' : line[:7],
                         'text' : line[9:]})
    return richtung

def parse_metabhf(zip,filename):
	# key: haltestellennummer1; haltestellennummer2
    l_content = zip.read(filename).decode(charset).split('\r\n')[:-1]
    metabhf_ubergangbeziehung = []
    metabhf_ubergangbeziehung_a = []
    metabhf_haltestellengruppen = []
    for i in range(len(l_content)):
        line = l_content[i]
        if len(l_content[i]) > 7 and l_content[i][7] == ':':
            sammelbegriffsnummer = line[:7]
            j = 10
            while j < len(line):
                j += 9
                haltestellennummer =  line[j:j+7].strip()
                if len (haltestellennummer) > 0:
                    metabhf_haltestellengruppen.append({'sammelbegriffsnummer' :sammelbegriffsnummer,
                                                        'haltestellennummer' : line[j:j+7]})
        else:
            if line[:2] == '*A':
                metabhf_ubergangbeziehung_a.append({'haltestellennummer1' : haltestellennummer1,
                                                    'haltestellennummer2' : haltestellennummer2,
                                                    'attributscode' : line[3:5]})
            else:
                haltestellennummer1 = line[:7]
                haltestellennummer2 = line[8:15]
                item = {'haltestellennummer1' : haltestellennummer1,
                        'haltestellennummer2' : haltestellennummer2,
                        'dauer' : line[16:19]}
                metabhf_ubergangbeziehung.append(item)
    return metabhf_ubergangbeziehung,metabhf_ubergangbeziehung_a,metabhf_haltestellengruppen

def parse_zugart(zip,filename):
	# key: code
    zugart = []
    zugart_category = {}
    zugart_class = {}
    angaben = False
    language = None
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '').replace('\n', '')
        if line == '':
            angaben = True
            continue
        if not angaben:
            item = {'code' : line[:3],
                    'produktklasse' : line[4:6],
                    'tarifgruppe' : line[7:8],
                    'ausgabesteuerung' : line[9:10],
                    'gattungsbezeichnung' : line[11:19].strip(),
                    'zuschlag' : line[20:21].strip(),
                    'flag' : line[22:23],
                    'gattungsbildernamen' : line[24:28].strip()}
            zugart.append(item)
            zugart_category[int(line[30:33])] = item
            zugart_class[int(item['produktklasse'])] = item
        else:
            if line == '<text>':
                continue
            elif line[0] == '<':
                language = line[1:-1].lower()
            elif line[:8] == 'category':
                zugart_category[int(line[8:11])]['category_'+language] = line[12:]
            #elif line[:6] == 'option': What does this do??
                #zugart_class[int(line[6:8])]['option_'+language] = line[9:]
            #elif line[:5] == 'class':
            #    zugart_class[int(line[5:7])]['class_'+language] = line[8:] #I dont think anyone cares for this, it's a superset of category
    return zugart

def parse_durchbi(zip,filename):
	# key: fahrtnummer1, verwaltungfahrt1, fahrtnummer2, verwaltungfahrt2, verkehrstagebitfeldnummer
    durchbi = []
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')

        item = { 'fahrtnummer1' : line[:5],
                 'verwaltungfahrt1': line[6:12],
                 'letzterhaltderfahrt1': line[13:20],
                 'fahrtnummer2': line[21:26],
                 'verwaltungfahrt2': line[27:33],
                 'verkehrstagebitfeldnummer': line[34:40],
                 'ersterhaltderfahrt2': line[41:48],
                 'attributmarkierungdurchbindung': line[49:51],
                 'kommentar': line[52:] }
        durchbi.append(item)
    return durchbi

def parse_zeitvs(zip,filename):
	# key: bahnhofsnummer
	# 1------+2----+3-----+4------+5---+6-------+7---+comment
	# 0000000 +0100 +0200 30032014 0200 26102014 0300 %  Nahverkehrsdaten; MEZ=GMT+1
	# 1 Haltestellennummer
	# 2 normal timedelta to gmt
	# 3 timesdelta to sommertime
	# 4 Begin of summertime date
	# 5 Begin of summertime time
	# 6 End of summerimte date
	# 7 End of summertime time

    zeitvs = {}
    for line in fileinput.input([filename], openhook=zip.open):
        line = line.decode(charset).replace('\r', '').replace('\n', '')
        if line[0] == '%':
            continue

        bahnhofsnummer = line[:7]

        if (len(line) >= 17 and line[16] != '%'):
            item = { 'bahnhofsnummer' : bahnhofsnummer,
                     'zeitverschiebung1': line[8:13].strip(),
                     'zeitverschiebung2': line[14:19].strip(), # timedelta to summertime
                     'vondatum': line[20:28].strip(),
                     'vonzugehorigezeit': line[29:33].strip(),
                     'bisdatum': line[34:42].strip(),
                     'biszugehorigezeit': line[43:47].strip(),
                     'kommentar': line[50:].strip() }
        else:
            item = zeitvs[line[8:15]].copy()
            item['bahnhofsnummer'] = bahnhofsnummer

        zeitvs[bahnhofsnummer] = item

    return zeitvs.values()

def filedict(zip):
    dict = {}
    for name in zip.namelist():
        dict[name] = name
    return dict

def sql_bitfeld(conn,bitfeld):
    f = StringIO()
    f.write('\t'.join(['bitfeldnummer', 'servicedate']) + '\n')
    for record in bitfeld:
        for date in record['dates']:
            f.write('\t'.join([record['bitfeldnummer'],str(date)])+'\n')
    f.seek(0)
    cur = conn.cursor()
    cur.copy_expert("COPY bitfeld FROM STDIN USING DELIMITERS '	' CSV HEADER NULL AS '';",f)
    cur.close()
    f.close()

def sql_fplan(conn,fplan):
    primary = ['id']
    simple_list_writer(conn,'fplan_z', primary +['fahrtnummer','verwaltung','variante','taktanzahl','takzeit'], fplan['Z'])
    simple_list_writer(conn,'fplan_g', primary +['verkehrsmittel','laufwegsindexab','laufwegsindexbis','indexab','indexbis'], fplan['G'])
    simple_list_writer(conn,'fplan_ave', primary +['laufwegsindexab','laufwegsindexbis','verkehrstagenummer','indexab','indexbis'], fplan['A_VE'])
    simple_list_writer(conn,'fplan_a', primary +['attributscode','laufwegsindexab','laufwegsindexbis','bitfeldnummer','indexab','indexbis'], fplan['A'])
    simple_list_writer(conn,'fplan_i', primary +['infotextcode','laufwegsindexab','laufwegsindexbis','bitfeldnummer','infotextnummer','indexab','indexbis'], fplan['I'])
    simple_list_writer(conn,'fplan_r', primary +['kennung','richtungscode','laufwegsindexab','laufwegsindexbis','indexab','indexbis'], fplan['R'])
    simple_list_writer(conn,'fplan_gr', primary +['grenzpunktnummer','laufwegsindexletzten','laufwegsindexersten','indexletzten','indexersten'], fplan['GR'])
    simple_list_writer(conn,'fplan_sh', primary +['laufwegindex','bitfeldnummer','indexfur'], fplan['SH'])
    simple_list_writer(conn,'fplan_l', primary +['liniennummer','laufwegsindexab','laufwegsindexbis','indexab','indexbis'], fplan['L'])
    simple_list_writer(conn,'fplan_laufweg', primary +['haltestellennummer','haltestellenname','ankunfstzeit','abfahrtszeit','fahrtnummer','verwaltung','x'], fplan['LAUFWEG'])


def load(path,filename):
    conn = psycopg2.connect("dbname='hafastmp' user='postgres'")

    zip = zipfile.ZipFile(path+'/'+filename,'r')
    files = filedict(zip)

    bahnhof = parse_bahnhof(zip,files['BAHNHOF'])
    simple_list_writer(conn,'bahnhof', ['haltestellennummer','name','longname','abkurzung','synonym'], bahnhof)
    bahnhof = None

    bfkoord = parse_bfkoord(zip,files['BFKOORD'])
    simple_list_writer(conn,'bfkoord', ['haltestellennummer','x','y','z'], bfkoord)
    bfkoord = None

    bfkoord_geo = parse_bfkoord_geo(zip,files['BFKOORD_GEO'])
    simple_list_writer(conn,'bfkoord_geo', ['haltestellennummer','x','y','z'], bfkoord_geo)
    bfkoord_geo = None

    eckdaten = parse_eckdaten(zip,files['ECKDATEN'])
    simple_list_writer(conn,'eckdaten', ['fahrplan_start','fahrplan_end','bezeichnung','fahrplan_periode','land','exportdatum','hrdf_version','lieferant'], [eckdaten])
    bitfeld = parse_bitfeld(zip,files['BITFELD'],eckdaten)
    sql_bitfeld(conn,bitfeld)
    eckdaten = None
    bitfeld = None

    zugart = parse_zugart(zip,files['ZUGART'])
    simple_list_writer(conn,'zugart', ['code','produktklasse','tarifgruppe','ausgabesteuerung','gattungsbezeichnung','zuschlag','flag','gattungsbildernamen','category_franzoesisch','category_italienisch','category_deutsch','category_englisch'], zugart)
    zugart = None

    metabhf_ubergangbeziehung,metabhf_ubergangbeziehung_a,metabhf_haltestellengruppen = parse_metabhf(zip,files['METABHF'])
    simple_list_writer(conn,'metabhf_ubergangbeziehung', ['haltestellennummer1','haltestellennummer2','dauer'], metabhf_ubergangbeziehung)
    simple_list_writer(conn,'metabhf_ubergangbeziehung_a', ['haltestellennummer1','haltestellennummer2','attributscode'], metabhf_ubergangbeziehung_a)
    simple_list_writer(conn,'metabhf_haltestellengruppen', ['sammelbegriffsnummer','haltestellennummer'], metabhf_haltestellengruppen)
    metabhf_ubergangbeziehung,metabhf_ubergangbeziehung_a,metabhf_haltestellengruppen = [None, None, None]

    umsteigb = parse_umsteigb(zip,files['UMSTEIGB'])
    simple_list_writer(conn,'umsteigb', ['haltestellennummer','umsteigezeit_ic','umsteigezeit'], umsteigb)
    umsteigb = None

    attribut1_de,attribut2_de = parse_attribut(zip,files['ATTRIBUT_DE'])
    simple_list_writer(conn,'attribut2_de', ['code','ausgabe_der_teilstrecke','einstellig'], attribut2_de)
    simple_list_writer(conn,'attribut1_de', ['code','haltestellenzugehorigkeit','attributsausgabeprioritat','attibutsausgabefeinsortierung','text'], attribut1_de)
    attribut1_de,attribut2_de = [None, None]

    attribut1_en,attribut2_en = parse_attribut(zip,files['ATTRIBUT_EN'])
    simple_list_writer(conn,'attribut2_en', ['code','ausgabe_der_teilstrecke','einstellig'], attribut2_en)
    simple_list_writer(conn,'attribut1_en', ['code','haltestellenzugehorigkeit','attributsausgabeprioritat','attibutsausgabefeinsortierung','text'], attribut1_en)
    attribut1_en,attribut2_en = [None, None]

    attribut1_fr,attribut2_fr = parse_attribut(zip,files['ATTRIBUT_FR'])
    simple_list_writer(conn,'attribut2_fr', ['code','ausgabe_der_teilstrecke','einstellig'], attribut2_fr)
    simple_list_writer(conn,'attribut1_fr', ['code','haltestellenzugehorigkeit','attributsausgabeprioritat','attibutsausgabefeinsortierung','text'], attribut1_fr)
    attribut1_fr,attribut2_fr = [None, None]

    attribut1_it,attribut2_it = parse_attribut(zip,files['ATTRIBUT_IT'])
    simple_list_writer(conn,'attribut2_it', ['code','ausgabe_der_teilstrecke','einstellig'], attribut2_it)
    simple_list_writer(conn,'attribut1_it', ['code','haltestellenzugehorigkeit','attributsausgabeprioritat','attibutsausgabefeinsortierung','text'], attribut1_it)
    attribut1_it,attribut2_it = [None, None]

    bfprios = parse_bfprios(zip,files['BFPRIOS'])
    simple_list_writer(conn,'bfprios', ['haltestellennummer','umsteigeprioritat'], bfprios)
    bfprios = None

    infotext_de = parse_infotext(zip,files['INFOTEXT_DE'])
    simple_list_writer(conn,'infotext_de', ['infotextnummer','informationstext'], infotext_de)
    infotext_de = None

    infotext_en = parse_infotext(zip,files['INFOTEXT_EN'])
    simple_list_writer(conn,'infotext_en', ['infotextnummer','informationstext'], infotext_en)
    infotext_en = None

    infotext_fr = parse_infotext(zip,files['INFOTEXT_FR'])
    simple_list_writer(conn,'infotext_fr', ['infotextnummer','informationstext'], infotext_fr)
    infotext_fr = None

    infotext_it = parse_infotext(zip,files['INFOTEXT_IT'])
    simple_list_writer(conn,'infotext_it', ['infotextnummer','informationstext'], infotext_it)
    infotext_it = None

    kminfo = parse_kminfo(zip,files['KMINFO'])
    simple_list_writer(conn,'kminfo', ['haltestellennummer','wert'], kminfo)
    kminfo = None

    umsteigv = parse_umsteigv(zip,files['UMSTEIGV'])
    simple_list_writer(conn,'umsteigv', ['haltestellennummer','verwaltungsbezeichnung1','verwaltungsbezeichnung2','mindestumsteigezeit'], umsteigv)
    umsteigv = None

    umsteigl = parse_umsteigl(zip,files['UMSTEIGL'])
    simple_list_writer(conn,'umsteigl', ['haltestellennummer','verwaltung1','gattung1','linie1','richtung1','verwaltung2','gattung2','linie2','richtung2','umsteigezeit','garantiert'], umsteigl)
    umsteigl = None

    umsteigz = parse_umsteigz(zip,files['UMSTEIGZ'])
    simple_list_writer(conn,'umsteigz', ['haltestellennummer','fahrtnummer1','verwaltung1','fahrtnummer2','verwaltung2','umsteigezeit','garantiert'], umsteigz)
    umsteigz = None

    #if 'VEREINIG' in files:
    #    vereinig = parse_vereinig(zip,files['VEREINIG'])
    durchbi = parse_durchbi(zip,files['DURCHBI'])
    simple_list_writer(conn,'durchbi', ['fahrtnummer1','verwaltungfahrt1','letzterhaltderfahrt1','fahrtnummer2','verwaltungfahrt2','verkehrstagebitfeldnummer','ersterhaltderfahrt2','attributmarkierungdurchbindung','kommentar'], durchbi)
    durchbi = None

    richtung = parse_richtung(zip,files['RICHTUNG'])
    simple_list_writer(conn,'richtung', ['richtingschlussel','text'], richtung)
    richtung = None

    zeitvs = parse_zeitvs(zip,files['ZEITVS'])
    simple_list_writer(conn,'zeitvs', ['bahnhofsnummer','zeitverschiebung1','zeitverschiebung2','vondatum','vonzugehorigezeit','bisdatum','biszugehorigezeit','kommentar'], zeitvs)
    zeitvs = None

    gleis = parse_gleis(zip,files['GLEIS'])
    simple_list_writer(conn,'gleis', ['haltestellennummer','fahrtnummer','verwaltung','gleisinformation','zeit','verkehrstageschlussel'], gleis)
    gleis = None

    betrieb1_de,betrieb2_de = parse_betrieb(zip,files['BETRIEB_DE'])
    simple_list_writer(conn,'betrieb1_de', ['betreibernummer','kurzname','langname','name'], betrieb1_de)
    simple_list_writer(conn,'betrieb2_de', ['betreibernummer','verwaltungen'], betrieb2_de)
    betrieb1_de,betrieb2_de = [None, None]


    betrieb1_en,betrieb2_en = parse_betrieb(zip,files['BETRIEB_EN'])
    simple_list_writer(conn,'betrieb1_en', ['betreibernummer','kurzname','langname','name'], betrieb1_en)
    simple_list_writer(conn,'betrieb2_en', ['betreibernummer','verwaltungen'], betrieb2_en)
    betrieb1_en,betrieb2_en = [None, None]


    betrieb1_it,betrieb2_it= parse_betrieb(zip,files['BETRIEB_IT'])
    simple_list_writer(conn,'betrieb1_it', ['betreibernummer','kurzname','langname','name'], betrieb1_it)
    simple_list_writer(conn,'betrieb2_it', ['betreibernummer','verwaltungen'], betrieb2_it)
    betrieb1_it,betrieb2_it = [None, None]


    betrieb1_fr,betrieb2_fr = parse_betrieb(zip,files['BETRIEB_FR'])
    simple_list_writer(conn,'betrieb1_fr', ['betreibernummer','kurzname','langname','name'], betrieb1_fr)
    simple_list_writer(conn,'betrieb2_fr', ['betreibernummer','verwaltungen'], betrieb2_fr)
    betrieb1_fr,betrieb2_fr = [None, None]

    dirwagen_kw,dirwagen_kwz,dirwagen_ave,dirwagen_a = parse_dirwagen(zip,files['DIRWAGEN'])
    simple_list_writer(conn,'dirwagen_kw', ['id', 'kurswagennummer'], dirwagen_kw)
    simple_list_writer(conn,'dirwagen_kwz', ['id','zugnummer','verhaltung','bahnhofsnummerab','bahnhofsname','bahnhofsnummerbis','abfahrtzeit1','abfahrtzeit2'], dirwagen_kwz)
    simple_list_writer(conn,'dirwagen_ave', ['id','laufwegindexab','laufwegindexbis','verkehrstagenummer'], dirwagen_ave)
    simple_list_writer(conn,'dirwagen_a', ['id','attributscode','laufwegsindexab','laufwegsindexbis','bitfeldnummer','indexab','indexbis'], dirwagen_a)
    dirwagen_kw,dirwagen_kwz,dirwagen_ave,dirwagen_a = [None, None, None, None]

    fplan = parse_fplan(zip,files['FPLAN'],conn)
    sql_fplan(conn,fplan)
    fplan = None

    conn.commit()
if __name__ == '__main__':
    load(sys.argv[1],sys.argv[2])
