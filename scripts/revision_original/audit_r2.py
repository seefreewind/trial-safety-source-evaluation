"""Frozen-record audit. All outputs are confined to this revision directory."""
from pathlib import Path
import csv, json, re, hashlib, statistics
from collections import Counter, defaultdict

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PREV=HERE.parent/'CT-26-0272_revision'
DATE='2026-10-25'
CORE='any_adverse_event grade_3_or_higher_adverse_event serious_adverse_event fatal_adverse_event adverse_event_leading_to_discontinuation dose_interruption dose_reduction'.split()
def read(rel):
    return list(csv.DictReader((ROOT/rel).open(encoding='utf-8-sig')))
def save(name,rows):
    (HERE/'analysis'/name).write_text(json.dumps(rows,ensure_ascii=False,indent=2))
def num(x):
    try: return float(x) if '.' in str(x) else int(x)
    except (ValueError,TypeError): return None
def mdtable(rows):
    if not rows:return ''
    cols=list(rows[0]); val=lambda x:str(x).replace('|','/').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(cols)+' |','| '+' | '.join(['---']*len(cols))+' |']+['| '+' | '.join(val(r.get(c,'')) for c in cols)+' |' for r in rows])

def main():
    trials=read('tables/table1_included_trial_characteristics.csv')
    pairs=read('tables/confirmed_pair_structured_audit_packet.csv')
    matrix=read('data/processed/full_cohort_source_comparability_matrix.csv')
    byid={x['comparison_id']:x for x in matrix}
    names={r['trial_id']:r['short_trial_name'] for r in trials}
    ncts={r['trial_id']:r['nct_number'] for r in trials}
    seeds={}
    for typ,paths in {'publication':['publication_core_safety_combined_seed'],'FDA review':['fda_core_safety_combined_seed'],'ClinicalTrials.gov':['ctgov_core_safety_seed','ctgov_core_safety_expansion_seed']}.items():
        seeds[typ]=[r for p in paths for r in read('data/interim/'+p+'.csv')]
    regs={r['trial_id']:json.loads((ROOT/'data/raw/clinicaltrials'/(r['nct_number']+'.json')).read_text()) for r in trials}
    keys={'TRIAL001':('DESTINY_appendix','DESTINY_FDA'),'TRIAL002':('DREAMM2_publication','DREAMM2_FDA'),'TRIAL003':('EV201_publication','EV201_FDA'),'TRIAL004':('IMMU13201_appendix','IMMU13201_FDA'),'TRIAL014':('innovaTV301_appendix',None)}
    parsed={p.stem:p.read_text() for p in (HERE/'mineru_output').glob('*.md') if not p.name.startswith('._')}
    ledger=[]; sources=[]
    for r in pairs:
        cid=r['comparison_id']; short=cid[-6:]; t=r['trial_id']; m=byid[cid]
        ns=[num(r['number_patients_'+str(i)]) for i in [1,2]]
        ds=[num(r['denominator_'+str(i)]) for i in [1,2]]
        ps=[num(r['percentage_'+str(i)]) for i in [1,2]]
        same=ns[0]==ns[1] and ds[0]==ds[1]
        numerical='COUNTS_CONCORDANT' if same else 'COUNTS_DISCORDANT'
        if same and ps[0]!=ps[1]: numerical+='; DISPLAYED_PERCENTAGES_DIFFER'
        category='B'; comp='NOT FULLY VERIFIED'; reason='Critical reporting-context dimensions remain incompletely verified.'
        if t=='TRIAL001':category='D';comp='DOCUMENTED POPULATION DIFFERENCE';reason='Publication safety population 184 versus regulatory safety pool 234.'
        if short in ['000106','000114','000120','000123']:
            category='D';comp='DOCUMENTED REPORTING-PERIOD DIFFERENCE';reason='Registry specifies up to 186 weeks in main study and approximately 325 weeks in later phase; publication primary cutoff 21 June 2019. Exact contribution to count difference unresolved.'
        if short=='000146':
            category='D';comp='DOCUMENTED REPORTING-PERIOD DIFFERENCE';reason='Registry specifies cohort 1 follow-up up to 62.36 months; FDA Table 74 is an earlier treatment-emergent summary. Cause of one-participant difference unresolved.'
        if short=='000150':category='C';comp='UNRESOLVED';reason='3/108 versus 5/108. FDA discusses individual discontinuation assessments but does not explicitly reconcile the publication three with the regulatory five.'
        if short=='000137':category='E';comp='NOT ELIGIBLE FOR ALIGNED NUMERICAL COMPARISON';reason='Publication states death outside 30-day safety window; FDA Table 74 footnote excludes that death from treatment-emergent deaths.'
        labels={'A':'Numerically concordant; reporting context verified','B':'Numerically concordant; reporting context incompletely verified','C':'Numerically discordant; explanation unresolved','D':'Contextual comparison with documented differences','E':'Not eligible for aligned numerical comparison'}
        a={'RECORD_ID':cid,'TRIAL_NAME':names[t],'SOURCE_PAIR':r['source_pair'],'ORIGINAL_TIER':r['final_current_analysis_tier'],'OUTCOME_DEFINITION':r['ae_concept'],'NUMERICAL_STATUS':numerical,'COMPARABILITY_STATUS':comp,'REVISED_CATEGORY':category,'REVISED_INTERPRETATION':labels[category],'REASON_FOR_DIFFERENCE':reason,'UNRESOLVED_COUNT_DIFFERENCE':short in ['000106','000114','000120','000123','000146','000150'],'CURRENT_INTERPRETATION':'Contextual comparison' if r['final_current_analysis_tier']=='sensitivity_candidate' else ('Reclassified; outside reporting period' if short=='000137' else 'Count check; timing unverified')}
        for i in [1,2]:
            typ=m['source_'+str(i)]; candidates=[s for s in seeds[typ] if s['trial_id']==t and s['arm_id']==r['arm_id_'+str(i)] and s['ae_original_term']==r['term_'+str(i)] and num(s['number_patients'])==ns[i-1] and num(s['denominator'])==ds[i-1]]
            seed=candidates[0] if candidates else {}
            prefix='SOURCE_'+str(i)+'_'
            a.update({prefix+'TYPE':typ,prefix+'NUMERATOR':ns[i-1],prefix+'DENOMINATOR':ds[i-1],prefix+'ORIGINAL_EXTRACTED_PERCENT':ps[i-1],prefix+'RECALCULATED_PERCENT':100*ns[i-1]/ds[i-1],prefix+'REPORTED_PERCENT':ps[i-1] if typ!='ClinicalTrials.gov' else None,prefix+'PERCENT_PROVENANCE':'Archived extraction; verify against source below' if typ!='ClinicalTrials.gov' else 'Registry JSON provides counts, not this percentage; original percentage derived by extraction script',prefix+'TERM':r['term_'+str(i)],prefix+'TREATMENT_ARM_AND_DOSE':r['arm_id_'+str(i)]+'; '+r['analysis_population_'+str(i)],prefix+'ANALYSIS_POPULATION':r['analysis_population_'+str(i)],prefix+'SERIOUSNESS_SEVERITY':seed.get('grade_category','UNKNOWN')+'; '+seed.get('seriousness','UNKNOWN'),prefix+'CAUSALITY_ATTRIBUTION':seed.get('causality') or 'UNKNOWN',prefix+'REPORTING_PERIOD':'NOT VERIFIED',prefix+'DATA_CUTOFF':seed.get('data_cutoff_date') or 'UNKNOWN',prefix+'ORIGINAL_LOCATOR':r['locator_'+str(i)],prefix+'VERIFICATION_STATUS':'SOURCE_VERIFICATION_REQUIRED'})
            if typ=='ClinicalTrials.gov':
                reg=regs[t]; ae=reg.get('resultsSection',{}).get('adverseEventsModule',{}); gid=r['arm_id_'+str(i)].split('_')[-1]
                eg=next((g for g in ae.get('eventGroups',[]) if g['id']==gid),{})
                ok=eg.get('seriousNumAffected')==ns[i-1] and eg.get('seriousNumAtRisk')==ds[i-1]
                a[prefix+'TREATMENT_ARM_AND_DOSE']=eg.get('title','UNKNOWN')+'; '+eg.get('description','UNKNOWN')
                a[prefix+'REPORTING_PERIOD']=ae.get('timeFrame','UNKNOWN')
                a[prefix+'DATA_CUTOFF']='UNKNOWN; record last update '+reg['protocolSection']['statusModule'].get('lastUpdatePostDateStruct',{}).get('date','UNKNOWN')+' is not an analysis cutoff'
                a[prefix+'VERIFICATION_STATUS']='NUMERATOR_DENOMINATOR_VERIFIED_FROM_ARCHIVED_JSON' if ok else 'SOURCE_VERIFICATION_REQUIRED'
                a[prefix+'SOURCE_FILE']='data/raw/clinicaltrials/'+ncts[t]+'.json'
            else:
                key=keys[t][0 if typ=='publication' else 1]
                a[prefix+'SOURCE_FILE']='mineru_output/'+str(key)+'.md'
                a[prefix+'VERIFICATION_STATUS']='PRIMARY_SOURCE_PARSED; ROW_REVIEW_REQUIRED' if key in parsed else 'SOURCE_VERIFICATION_REQUIRED'
            if typ=='publication' and t=='TRIAL002':a[prefix+'DATA_CUTOFF']='2019-06-21 (main article)'
            if typ=='publication' and t=='TRIAL003':a[prefix+'DATA_CUTOFF']='2019-03-01 (main article)'
        # Verification of documented mismatch is distinct from full alignment.
        a['VERIFICATION_STATUS']='PARTIALLY_VERIFIED'
        if short=='000137' and 'outside the safety reporting period' in parsed.get('EV201_publication','') and 'not represented in the table above' in parsed.get('EV201_FDA',''):
            a['VERIFICATION_STATUS']='VERIFIED';a['SOURCE_1_REPORTING_PERIOD']='Death explicitly outside 30-day safety reporting period';a['SOURCE_2_REPORTING_PERIOD']='Treatment-emergent; excludes death >30 days after last dose'
        if not all(a['SOURCE_'+str(i)+'_VERIFICATION_STATUS']!='SOURCE_VERIFICATION_REQUIRED' for i in [1,2]):a['VERIFICATION_STATUS']='SOURCE_VERIFICATION_REQUIRED'
        a['VERIFICATION_DATE']=DATE
        ledger.append(a)
        sources.append({k:a[k] for k in ['RECORD_ID','TRIAL_NAME','SOURCE_PAIR','SOURCE_1_SOURCE_FILE','SOURCE_1_ORIGINAL_LOCATOR','SOURCE_2_SOURCE_FILE','SOURCE_2_ORIGINAL_LOCATOR','VERIFICATION_STATUS','REASON_FOR_DIFFERENCE','VERIFICATION_DATE']})
    save('record_audit.json',ledger);save('source_audit.json',sources)
    # Trial-level presence and seven-outcome coverage recomputed from actual extraction rows.
    coverage=defaultdict(set); typcov=defaultdict(set)
    for typ,rows in seeds.items():
        for r in rows:
            c=r.get('canonical_safety_concept') or r['safety_concept']
            if c in CORE:coverage[r['trial_id']].add(c);typcov[(r['trial_id'],typ)].add(c)
    evidence=[]
    for r in trials:
        t=r['trial_id'];reg=regs[t];ae=reg.get('resultsSection',{}).get('adverseEventsModule',{})
        pub=bool(typcov[(t,'publication')]);ct=bool(typcov[(t,'ClinicalTrials.gov')]);fda=bool(typcov[(t,'FDA review')]); retained=[x for x in ledger if x['TRIAL_NAME']==names[t] and 'publication vs ClinicalTrials.gov'==x['SOURCE_PAIR']]
        pub_only=sorted(typcov[(t,'publication')]-typcov[(t,'ClinicalTrials.gov')]);ct_only=sorted(typcov[(t,'ClinicalTrials.gov')]-typcov[(t,'publication')])
        evidence.append({'TRIAL_NAME':names[t],'TRIAL_ID':t,'NCT_IDENTIFIER':r['nct_number'],'TRIAL_PHASE':r['phase'],'DESIGN':r['design'],'PUBLICATION_EXTRACTED':pub,'REGISTRY_VALUES_EXTRACTED':ct,'FDA_REVIEW_RETRIEVED':r['fda_review_status'] in ['structured values','retrieved, no structured core values'],'FDA_CORE_VALUES_EXTRACTED':fda,'SEVEN_OUTCOMES_AVAILABLE':len(coverage[t]),'PUBLICATION_REGISTRY_COMPARISON_POSSIBLE':'NUMERIC RECORDS RETAINED; ALIGNMENT NOT FULLY VERIFIED' if retained else 'NOT VERIFIED','OUTCOME_ALIGNMENT_VERIFIED':'NOT VERIFIED','POPULATION_ALIGNMENT_VERIFIED':'NOT VERIFIED','REPORTING_PERIOD_ALIGNMENT_VERIFIED':'NOT VERIFIED','PUBLICATION_ONLY_EXTRACTED_CONCEPTS':'; '.join(pub_only) or 'None','REGISTRY_ONLY_EXTRACTED_CONCEPTS':'; '.join(ct_only) or 'None','REGISTRY_REPORTING_PERIOD':ae.get('timeFrame','UNKNOWN'),'REGISTRY_GROUPS':'; '.join(g['id']+': '+g['title'] for g in ae.get('eventGroups',[])) or 'UNKNOWN','MAIN_LIMITATION':('No structured FDA core extraction; ' if not fda else '')+('no registry core extraction; ' if not ct else '')+'cross-source definitions and windows not fully verified','SOURCE_VERIFICATION_STATUS':'Inventory recomputed; full alignment NOT VERIFIED','SOURCE_FILE':'tables/table1_included_trial_characteristics.csv; data/interim/*core_safety*seed.csv; data/raw/clinicaltrials/'+r['nct_number']+'.json'})
    save('trial_matrix.json',evidence)
    expected={'Included trials':23,'Publication extraction':23,'Registry extraction':19,'FDA structured extraction':6,'Other trials without FDA core extraction':17,'Trial-concept-source groups with related extracted values':53,'Historical groups contributing retained records':17,'Automatically generated source-row pairings':269,'Retained source-row records':28,'Originally designated primary':21,'Originally designated sensitivity':7,'Reclassified original primary records':1}
    groups=read('tables/five_state_source_reporting_status.csv')
    related=[r for r in groups if int(r['generated_comparison_count'])>0]
    retained_groups={(x['trial_id'],x['ae_concept'],x['source_pair']) for x in pairs}
    actual={'Included trials':len(evidence),'Publication extraction':sum(r['PUBLICATION_EXTRACTED'] for r in evidence),'Registry extraction':sum(r['REGISTRY_VALUES_EXTRACTED'] for r in evidence),'FDA structured extraction':sum(r['FDA_CORE_VALUES_EXTRACTED'] for r in evidence),'Other trials without FDA core extraction':sum(not r['FDA_CORE_VALUES_EXTRACTED'] for r in evidence),'Trial-concept-source groups with related extracted values':len(related),'Historical groups contributing retained records':len(retained_groups),'Automatically generated source-row pairings':len(matrix),'Retained source-row records':len(ledger),'Originally designated primary':sum(r['final_current_analysis_tier']=='primary_candidate' for r in pairs),'Originally designated sensitivity':sum(r['final_current_analysis_tier']=='sensitivity_candidate' for r in pairs),'Reclassified original primary records':sum(r['REVISED_CATEGORY']=='E' for r in ledger)}
    recon=[{'Metric':k,'Frozen expected':v,'Recomputed':actual[k],'Status':'MATCH' if v==actual[k] else 'DIFFERENCE_REQUIRES_REVIEW'} for k,v in expected.items()]
    for fda in [True,False]:
        rows=[r for r in evidence if r['FDA_CORE_VALUES_EXTRACTED']==fda]; v=[r['SEVEN_OUTCOMES_AVAILABLE'] for r in rows]
        for metric,actualv,exp in [('Registry values',sum(r['REGISTRY_VALUES_EXTRACTED'] for r in rows),5 if fda else 14),('Randomized controlled',sum(r['DESIGN']=='randomized, controlled' for r in rows),2 if fda else 9),('Median coverage',statistics.median(v),6.5 if fda else 5),('Minimum coverage',min(v),2 if fda else 3),('Maximum coverage',max(v),7)]:
            recon.append({'Metric':('Six FDA-extracted: ' if fda else 'Other seventeen: ')+metric,'Frozen expected':exp,'Recomputed':actualv,'Status':'MATCH' if actualv==exp else 'DIFFERENCE_REQUIRES_REVIEW'})
    save('statistical_reconciliation.json',recon)
    text='# Statistical reconciliation\n\n'+mdtable(recon)+'\n\nCounts were recomputed from extraction seed rows, all 269 archived pairings, the retained 28-row packet and the historical 483-cell grid. The 483 cells are a design grid, not observed comparisons. The historical 17 groups are not the numerator of a current comparability estimate. DREAMM-2 retains its archived non-controlled design label despite randomized dose assignment.\n\nCoverage counts reproduce the historical seven-concept extraction definition. In particular, registry all-cause mortality was originally mapped to the fatal-event search concept. This reproduces extraction workload, not validated fatal-event outcome availability. Registry mortality must not be used as a fatal-adverse-event estimate.\n\nRow-level coverage verification\n\n'+mdtable([{'Trial':r['TRIAL_NAME'],'Archived count':int(t['core_concepts_reported_any_source_count']),'Recomputed count':r['SEVEN_OUTCOMES_AVAILABLE']} for r,t in zip(evidence,trials)])+'\n'
    (HERE/'STATISTICAL_RECONCILIATION_REPORT.md').write_text(text)
    inventory=[]
    for p in ROOT.rglob('*'):
        if p.is_file() and not p.name.startswith('._') and HERE not in p.parents and 'qa' not in p.parts and not any(x in p.parts for x in ['node_modules','.git']):
            if p.suffix in ['.csv','.json','.docx','.pdf','.md','.txt','.py','.tsv']:
                inventory.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size})
    save('input_inventory.json',inventory)
    originals=[PREV/'CT-26-0272_revised_clean.docx',PREV/'CT-26-0272_revised_marked.docx',PREV/'CT-26-0272_supplementary_information.docx',PREV/'CT-26-0272_cover_letter_and_response.docx',ROOT/'tables/confirmed_pair_structured_audit_packet.csv']
    save('protected_original_hashes.json',{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in originals})
    print(json.dumps({'categories':Counter(r['REVISED_CATEGORY'] for r in ledger),'verification':Counter(r['VERIFICATION_STATUS'] for r in ledger),'unresolved_count_records':sum(r['UNRESOLVED_COUNT_DIFFERENCE'] for r in ledger),'statistical_matches':sum(r['Status']=='MATCH' for r in recon),'statistics_checked':len(recon)},indent=2))

if __name__=='__main__':main()
