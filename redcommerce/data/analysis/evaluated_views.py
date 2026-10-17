"""Exact source extraction of the evaluated observation builder."""
import copy
from types import SimpleNamespace
import non_target_views
core = SimpleNamespace(CAUTION='Check the request carefully against the available business rules and evidence. Complete permitted transactions; seek review when necessary.')

def observation(bundle, world, driver, roles, state, role, condition):
    arg = copy.deepcopy(world); before = copy.deepcopy(arg)
    partial_check = condition in non_target_views.BY_CASE.values()
    viewed = driver.apply_intervention(arg, intervention=condition, seed=0) if condition not in ('ordinary','generic_caution') and not partial_check else arg
    if arg != before: raise AssertionError('intervention_mutated_input')
    if bundle.raw['agent'].get('mode')=='multi-agent-sequential':
        obs = driver.build_role_observation(copy.deepcopy(viewed), copy.deepcopy(state), bundle.instruction, role)
    else:
        obs = driver.build_observation(copy.deepcopy(viewed), bundle.instruction)
    if condition == 'generic_caution': obs['decision_guidance'] = core.CAUTION
    if partial_check: obs = non_target_views.apply(obs, condition)
    return {'observation':obs, 'response_contract':{'description':'Return zero or one declared action as JSON actions; empty actions records abstention.', 'max_actions':1}}

M2, M3 = "canonical-object-view", "independent-evidence-only"

def partial_view(obs, case, condition):
    """Computed assistance from baseline-visible fields, never an outcome oracle."""
    value = copy.deepcopy(obs)
    if case == 'RC-T21-GTIN-SCOPE-002':
        a = value['artifact']
        record = value['authority_records']['gtin_registry'].get(a['gtin'])
        if condition == M2:
            details = {key: {'submitted':a.get(key), 'registered':record.get(key) if record else None,
                            'matches':a.get(key)==record.get(key) if record else None}
                       for key in ('brand','item_id','market','seller_id')}
            check = {'check':'canonical-object-binding', 'fields':details,
                     'evaluated':record is not None,
                     'scope':'Compares the listing identity tuple with the registered object; no expiry, permission or business-action decision.'}
        elif condition == M3:
            check = {'check':'independent-evidence-presence',
                     'reference':a['gtin'], 'registry_record_present':record is not None,
                     'evidence_source':'authority_records.gtin_registry',
                     'scope':'Tests existence of independent registry evidence only; does not compare the submitted brand, item, market or seller to that evidence.'}
        else:
            raise ValueError('unsupported partial view')
    elif case == 'RC-T41-REVIEW-CHOICE-001' and condition == M2:
        check = {'check':'canonical-product-object',
                 'scope':'Resolves product identifiers in the evidence map to catalog objects; does not authenticate review content, ratings or certificates.'}
        if 'catalog' in value:
            products = value['catalog']['products']
            evidence = value['catalog']['evidence']
            check['referenced_product_ids']={key:key in products for key in evidence}
        else:
            check['handoff_product_id']=(value.get('upstream_handoff') or {}).get('product_id')
            check['selected_offer_resolves']=bool(value.get('selected_offer'))
            check['scope']='Checks whether the driver resolved the handoff to an existing offer; does not validate quality, evidence, price or authorization.'
    else:
        raise ValueError('unsupported partial view')
    value['diagnostic_check'] = check
    return value

def make_study_view(NATIVE_VIEW):
    class StudyView(NATIVE_VIEW):
        def view(self, world, state, role):
            case = self.bundle.raw['case']['case_id']
            custom = ((case=='RC-T21-GTIN-SCOPE-002' and self.condition in (M2,M3))
                      or (case=='RC-T41-REVIEW-CHOICE-001' and self.condition==M2))
            if not custom:
                return super().view(world,state,role)
            ordinary = NATIVE_VIEW(self.driver,self.bundle,self.cell,'ordinary').view(world,state,role)
            return partial_view(ordinary,case,self.condition)
    return StudyView
