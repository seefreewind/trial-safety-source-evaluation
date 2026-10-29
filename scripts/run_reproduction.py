"""Run original builders and recalculate descriptive outputs from archived inputs.

The annotation ledger is a manual source-audit INPUT, never independent adjudication.
Expected numbers are loaded only after outputs have been computed.
"""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,csv,json,hashlib,importlib.util,sys,platform,statistics,html,re,shutil

BASE=Path(__file__).resolve().parents[1]
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,r):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(r[0]));w.writeheader();w.writerows(r)
def load(n):
    spec=importlib.util.spec_from_file_location(n,BASE/'scripts/original'/(n+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def flat(x,p=''):
    if isinstance(x,dict):return {k:v for a,b in x.items() for k,v in flat(b,p+'/'+a).items()}
    if isinstance(x,list):return {k:v for a,b in enumerate(x) for k,v in flat(b,p+'/'+str(a)).items()}
    return {p:x}
def fmt(s):return ' '.join(re.sub(r'\\+([\[\]^])',r'\1',html.unescape(s)).split())

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,required=True);args=ap.parse_args()
    out=args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Output directory must be new or empty; no prior files overwritten.')
    out.mkdir(parents=True,exist_ok=True)
    for n in ['tables','data/processed','protocol','manuscript']:(out/n).mkdir(parents=True,exist_ok=True)
    tests=[]
    def check(n,ok,detail=''):
        tests.append({'test':n,'pass':bool(ok),'detail':detail});print(('PASS ' if ok else 'FAIL ')+n,flush=True)
    data=BASE/'data';expected=data/'tables'
    # Original candidate generator. Only paths change; old scientific rules remain unchanged.
    m=load('build_full_cohort_source_comparability_matrix')
    m.ROOT=out;m.INTERIM=data/'data/interim';m.OUT_MATRIX=out/'data/processed/full_cohort_source_comparability_matrix.csv';m.OUT_SUMMARY=out/'tables/candidate_summary.csv';m.REPORT_OUT=out/'protocol/legacy_candidate_report.md';m.main()
    generated=rows(m.OUT_MATRIX);archived=rows(data/'data/processed/full_cohort_source_comparability_matrix.csv')
    check('Original candidate generator matches every archived row and field',generated==archived)
    # Existing packet builder combines confirmation inputs, detail and audit inputs.
    m=load('build_manual_adjudication_packets');m.CONFIRMED_IN=expected/'analysis_ready_comparison_set_confirmed.csv';m.MATRIX=data/'data/processed/full_cohort_source_comparability_matrix_detail.csv';m.AUDIT=expected/'final_analysis_audit_index.csv'
    pairs=m.build_pair_review_packet();write(out/'tables/retained_packet.csv',pairs)
    check('Original retained-record builder matches archived packet',pairs==rows(expected/'confirmed_pair_structured_audit_packet.csv'))
    # Run historical screening builder in isolation, never treating old A/B/C as revised A-E.
    # Only its input reader is routed to packaged inputs or already regenerated matrix.
    m=load('build_three_layer_analysis_tables');m.ROOT=out;m.DATA=out/'data';m.TABLES=out/'tables';m.MANUSCRIPT=out/'manuscript';m.PROTOCOL=out/'protocol'
    def route(p):
        rel=p.relative_to(out)
        return rows(p if p.exists() else data/rel)
    m.read_rows=route;m.main()
    five=rows(out/'tables/five_state_source_reporting_status.csv')
    check('Historical screening regenerated row-for-row',five==rows(expected/'five_state_source_reporting_status.csv'))
    # Source-flow script distinguishes source presence from extraction.
    m=load('build_source_flow_status');m.ROOT=out;m.COMPLETENESS=out/'tables/core_safety_reporting_completeness_by_trial_source.csv';m.SOURCE_INV=expected/'source_citation_inventory.csv';m.SOURCE_STATUS=expected/'full_cohort_expansion_source_status.csv';m.FIVE_STATE=out/'tables/five_state_source_reporting_status.csv'
    for k,n in [('TRIAL_SOURCE_OUT','tables/source_flow_status_by_trial_source.csv'),('SOURCE_SUMMARY_OUT','tables/source_flow_status_summary.csv'),('CONCEPT_OUT','tables/source_flow_status_by_trial_source_concept.csv'),('MANUSCRIPT_OUT','manuscript/legacy_source_flow.md'),('REPORT_OUT','protocol/legacy_source_flow.md')]:setattr(m,k,out/n)
    m.main()
    m=load('build_manuscript_figures_tables');m.TABLES=out/'tables';trials=m.build_table1()
    check('Original trial-characteristics builder matches all fields',trials==rows(expected/'table1_included_trial_characteristics.csv'))
    # Recompute coverage directly from seed rows, not from final Word or Excel outputs.
    core=set('any_adverse_event grade_3_or_higher_adverse_event serious_adverse_event fatal_adverse_event adverse_event_leading_to_discontinuation dose_interruption dose_reduction'.split())
    coverage=defaultdict(set);src=defaultdict(set);seeds={}
    for typ,files in [('publication',['publication_core_safety_combined_seed']),('FDA review',['fda_core_safety_combined_seed']),('ClinicalTrials.gov',['ctgov_core_safety_seed','ctgov_core_safety_expansion_seed'])]:
        seeds[typ]=[]
        for n in files:
            for r in rows(data/'data/interim'/(n+'.csv')):
                seeds[typ].append(r);c=r.get('canonical_safety_concept') or r['safety_concept']
                if c in core:coverage[r['trial_id']].add(c);src[r['trial_id'],typ].add(c)
    trial_output=[]
    for t in trials:
        tid=t['trial_id'];trial_output.append(dict(t,publication=bool(src[tid,'publication']),registry=bool(src[tid,'ClinicalTrials.gov']),fda=bool(src[tid,'FDA review']),recomputed_coverage=len(coverage[tid]),publication_only_concepts='; '.join(sorted(src[tid,'publication']-src[tid,'ClinicalTrials.gov'])),registry_only_concepts='; '.join(sorted(src[tid,'ClinicalTrials.gov']-src[tid,'publication']))))
    write(out/'trial_level_summary.csv',trial_output)
    check('All trial coverage counts match archived counts',all(r['recomputed_coverage']==int(r['core_concepts_reported_any_source_count']) for r in trial_output))
    ledger=json.loads((data/'revision_inputs/record_audit.json').read_text());pairby={r['comparison_id']:r for r in pairs}
    record_output=[]
    for a in ledger:
        p=pairby[a['RECORD_ID']];ok=True
        for i in [1,2]:
            n=float(p[f'number_patients_{i}']);d=float(p[f'denominator_{i}']);typ=a[f'SOURCE_{i}_TYPE']
            # Three historical DESTINY packet records have blank arm IDs. A blank
            # is not an arm match: require a unique source/term/n/N seed link.
            matches=[s for s in seeds[typ] if s['trial_id']==p['trial_id'] and (not p[f'arm_id_{i}'] or s['arm_id']==p[f'arm_id_{i}']) and s['ae_original_term']==p[f'term_{i}'] and float(s['number_patients'])==n and float(s['denominator'])==d]
            if not p[f'arm_id_{i}']:ok &= len(matches)==1
            ok &= bool(matches) and n==a[f'SOURCE_{i}_NUMERATOR'] and d==a[f'SOURCE_{i}_DENOMINATOR'] and abs(100*n/d-a[f'SOURCE_{i}_RECALCULATED_PERCENT'])<1e-10
        numerical_same=float(p['number_patients_1'])==float(p['number_patients_2']) and float(p['denominator_1'])==float(p['denominator_2'])
        check('Record '+a['RECORD_ID']+' linked to original seed rows',ok and p['final_current_analysis_tier']==a['ORIGINAL_TIER'])
        record_output.append({'record_id':a['RECORD_ID'],'trial_id':p['trial_id'],'n1':p['number_patients_1'],'N1':p['denominator_1'],'n2':p['number_patients_2'],'N2':p['denominator_2'],'counts_equal_recomputed':numerical_same,'category_manual_input':a['REVISED_CATEGORY'],'interpretation_status_manual_input':a['VERIFICATION_STATUS'],'context_alignment_certified_manual_input':a['CONTEXT_ALIGNMENT_CERTIFIED'],'original_tier':p['final_current_analysis_tier'],'source_1_percent_display_or_derived':p['percentage_1'],'source_2_percent_display_or_derived':p['percentage_2'],'seed_linkage_scope':'Unique source/term/n/N linkage; packet arm ID missing, not inferred aligned' if not p['arm_id_1'] or not p['arm_id_2'] else 'Arm/source/term/n/N linkage','reason_manual_input':a['REASON_FOR_DIFFERENCE']})
    write(out/'record_level_audit.csv',record_output)
    counts=Counter(r['category_manual_input'] for r in record_output)
    write(out/'classification_summary.csv',[{'category':k,'count':counts[k],'scope':'Count of supplied source-audit judgments; not a new independent adjudication.'} for k in 'ABCDE'])
    check('Ledger count matches rebuilt packet and unique IDs',len(ledger)==len(pairs)==len(pairby) and {r['RECORD_ID'] for r in ledger}==set(pairby))
    check('Concordant revised category requires equal counts',all(r['counts_equal_recomputed'] for r in record_output if r['category_manual_input'] in ['A','B']))
    check('No record certified fully context-aligned',not any(a['CONTEXT_ALIGNMENT_CERTIFIED'] for a in ledger))
    # n/N source checks against original registry JSON; no new claim-level text extraction.
    for a in ledger:
        for i in [1,2]:
            if a[f'SOURCE_{i}_TYPE']!='ClinicalTrials.gov':continue
            p=pairby[a['RECORD_ID']];g=p[f'arm_id_{i}'].split('_')[-1]
            study=json.loads((data/'data/raw/clinicaltrials'/(a['NCT_IDENTIFIER']+'.json')).read_text());group=next(x for x in study['resultsSection']['adverseEventsModule']['eventGroups'] if x['id']==g)
            check('Registry source n/N '+a['RECORD_ID']+' side '+str(i),group['seriousNumAffected']==a[f'SOURCE_{i}_NUMERATOR'] and group['seriousNumAtRisk']==a[f'SOURCE_{i}_DENOMINATOR'])
    actual={'Included trials':len(trials),'Publication extraction':sum(r['publication'] for r in trial_output),'Registry extraction':sum(r['registry'] for r in trial_output),'FDA structured extraction':sum(r['fda'] for r in trial_output),'Other trials without FDA core extraction':sum(not r['fda'] for r in trial_output),'Trial-concept-source groups with related extracted values':sum(int(r['generated_comparison_count'])>0 for r in five),'Historical groups contributing retained records':len({(r['trial_id'],r['ae_concept'],r['source_pair']) for r in pairs}),'Automatically generated source-row pairings':len(generated),'Retained source-row records':len(pairs),'Originally designated primary':sum(r['final_current_analysis_tier']=='primary_candidate' for r in pairs),'Originally designated sensitivity':sum(r['final_current_analysis_tier']=='sensitivity_candidate' for r in pairs),'Reclassified original primary records':counts['E']}
    groups=[]
    for flag in [True,False]:
        rr=[r for r in trial_output if r['fda']==flag];v=[r['recomputed_coverage'] for r in rr];prefix='Six FDA-extracted: ' if flag else 'Other seventeen: '
        st={'Registry values':sum(r['registry'] for r in rr),'Randomized controlled':sum(r['design']=='randomized, controlled' for r in rr),'Median coverage':statistics.median(v),'Minimum coverage':min(v),'Maximum coverage':max(v)}
        actual.update({prefix+k:v for k,v in st.items()});groups.append({'fda_structured_extraction':flag,'trials':len(rr),**st})
    write(out/'table2_regenerated.csv',groups)
    spec=importlib.util.spec_from_file_location('r1_original',BASE/'scripts/revision_original/revise_package.py');r1=importlib.util.module_from_spec(spec);spec.loader.exec_module(r1)
    r1.ROOT=data;r1.DATA=out/'r1_reanalysis';r1.DATA.mkdir()
    _,_,r1groups,_=r1.analyse()
    check('Original pandas six-versus-seventeen reanalysis agrees',all(int(r1groups.iloc[i]['Trials'])==g['trials'] and int(r1groups.iloc[i]['Registry values'])==g['Registry values'] and int(r1groups.iloc[i]['Randomized controlled'])==g['Randomized controlled'] for i,g in enumerate(groups)))
    # Expectations are assertions, never sources for any computed result above.
    expected_stats=json.loads((data/'revision_inputs/statistical_reconciliation.json').read_text())
    reconciliation=[]
    for r in expected_stats:
        val=actual[r['Metric']];check('Statistic '+r['Metric'],val==r['Frozen expected'])
        reconciliation.append({'metric':r['Metric'],'reported':r['Frozen expected'],'recomputed':val,'matches':val==r['Frozen expected']})
    write(out/'statistical_reconciliation.csv',reconciliation)
    old=json.loads((data/'historical_versions/NCT04484623_official_api_version_20.json').read_text())['study'];new=json.loads((data/'historical_versions/NCT04484623_official_api_version_21.json').read_text())['study'];arch=json.loads((data/'data/raw/clinicaltrials/NCT04484623.json').read_text())
    ae=old['resultsSection']['adverseEventsModule'];ae2=new['resultsSection']['adverseEventsModule'];fa=flat(ae);fb=flat(arch['resultsSection']['adverseEventsModule']);diff=[k for k in fa.keys()|fb.keys() if fa.get(k)!=fb.get(k)]
    check('Official historical adverse-event modules equal',ae==ae2)
    check('Historical version publicly posted before identification cutoff',old['protocolSection']['statusModule']['lastUpdatePostDateStruct']['date']<='2026-05-31')
    check('Archive differences are text formatting only',all(isinstance(fa[k],str) and isinstance(fb[k],str) and fmt(fa[k])==fmt(fb[k]) for k in diff))
    eg={g['id']:g for g in ae['eventGroups']};ns=[]
    for r in seeds['ClinicalTrials.gov']:
        if r['document_id']!='CTGOV_NCT04484623':continue
        g=eg[r['arm_id'].split('_')[-1]];n,d={'All-cause mortality':('deathsNumAffected','deathsNumAtRisk'),'Participants affected by serious adverse events':('seriousNumAffected','seriousNumAtRisk'),'Participants affected by other non-serious adverse events':('otherNumAffected','otherNumAtRisk')}[r['ae_original_term']]
        ns.append({'record':r['observation_id'] if 'observation_id' in r else r.get('ae_record_id',''),'n':int(r['number_patients']),'N':int(r['denominator']),'matches':int(r['number_patients'])==g[n] and int(r['denominator'])==g[d]})
    check('All extracted DREAMM-8 n/N match historical source',bool(ns) and all(r['matches'] for r in ns))
    (out/'historical_verification.json').write_text(json.dumps({'leaf_fields':len(fa),'format_difference_paths':sorted(diff),'extraction_checks':ns,'historical_public_date':old['protocolSection']['statusModule']['lastUpdatePostDateStruct']['date']},indent=2))
    write(out/'source_coverage_counts.csv',[{'source':s,'trials':sum(bool(src[t['trial_id'],s]) for t in trials)} for s in seeds])
    write(out/'historical_screening_counts.csv',[{'metric':k,'recomputed':v} for k,v in actual.items() if k in ['Trial-concept-source groups with related extracted values','Historical groups contributing retained records','Automatically generated source-row pairings','Retained source-row records','Originally designated primary','Originally designated sensitivity']])
    import pandas,docx,numpy,matplotlib
    result={'python':platform.python_version(),'pandas':pandas.__version__,'python_docx':docx.__version__,'numpy':numpy.__version__,'matplotlib':matplotlib.__version__,'tests_passed':sum(x['pass'] for x in tests),'tests_total':len(tests),'all_passed':all(x['pass'] for x in tests),'categories':{k:counts[k] for k in 'ABCDE'},'interpretation_status':dict(Counter(a['VERIFICATION_STATUS'] for a in ledger)),'tests':tests,'REPRODUCIBILITY_STATUS':'PASS_EXTRACTED_DATA' if all(x['pass'] for x in tests) else 'FAILED','END_TO_END_SOURCE_REEXTRACTION':'PARTIAL: existing extraction seeds, original confirmation and manual source-audit annotations are inputs; copyrighted primary-text extraction and independent human adjudication are not repeated.','randomness':'None in the functions executed. No inferential analysis, bootstrap or training run.'}
    (out/'test_results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='tests'},indent=2))
    if not result['all_passed']:raise SystemExit(1)
if __name__=='__main__':main()
