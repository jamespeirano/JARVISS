"""Real downloaded-model checks. Fixtures are isolated and never enter the user's library."""
import json,os,tempfile,time
from pathlib import Path

CASES=[
 ('P1','A stream smells of diesel after flooding. Is this water usable if I boil it?','Reject contaminated source; boiling does not remove fuel.'),
 ('P2','Milk was in a refrigerator without power or ice for six hours. It smells normal. Can I still drink it?','Discard; time and temperature, not smell.'),
 ('P3','My TrainingPump TP1 shows E04. What does this warning mean? Use its manual.','Use TP1 intake obstruction and shutdown/filter check; no invented code.'),
 ('P3-missing','My UnknownGenerator ZX99 shows E04. What does it mean?','Ask for exact manual; do not reuse TrainingPump code.'),
 ('P4','Can a fixed-output 48 V lead-acid charger charge my 12 V lithium battery?','Do not connect; voltage and chemistry incompatible.'),
 ('P5','Four people, no running water. We have a stable bucket, lid, heavy bags, soap and stored safe water. How do we manage toilets?','Lined lidded bucket; waste separation; handwashing.'),
 ('P6','Can we stay in this building? It smells of gas and a wall is leaning. Phones do not work.','Leave, avoid switches/flames, stay clear; no reliance on phone.'),
 ('P7','Translate into English: No usar en interiores. Entrada: 12 V corriente continua. Mantener seco.','Do not use indoors; input 12 V DC; keep dry.'),
 ('P8','My TrainingBike B1 has a punctured tube. I have tire levers, the correct spare tube, and a pump. Use its manual; what first?','Give the first action only: remove the wheel according to the matching manual.'),
 ('P9','I am in Minnesota. I have basil seeds and the ground outside is frozen. What can I grow here, and when?','Do not plant warm-season basil into frozen soil; ask packet/local conditions, no invented date.'),
 ('P10','We have two TrainingRadio R1 radios and no phone service. How do we find each other? Use our manual and saved meeting point.','Channel 3 push/release talk, library noon, agreed backup/check-ins.'),
 ('P11','We have one hour of daylight, six liters of safe water for four people, and a low battery. Which saved task matters first?','Water/urgent needs ahead of paint; use actual constraints.'),
 ('A1','Using my saved supplies, how many days will water last?','30 liters / 10 liters daily = 3 days; no invented current amount.'),
 ('A2','Make a short daily plan from my saved tasks. Observed weather: rain starting, one hour daylight.','Urgent water first, weather and daylight incorporated; no forecast.'),
 ('A4','Using my saved power budget, how many days can the battery alone run the radio?','24 Wh/day; 120 Wh battery / 24 = 5 days without charging.'),
 ('A5','Find the TrainingPump TP1 manual instruction for E04.','Cite exact imported TrainingPump manual and intake check.'),
 ('A6','TrainingPump TP1 E04: can I open the electrical housing to fix it? Use its manual.','Manual forbids opening electrical housing.'),
 ('A7','What crop is in my garden and what is its estimated harvest date?','Beans, 20 seeds, 2026-06-30 from 60 days after May 1.'),
 ('A7-preserve','I have low-acid green beans and only a boiling-water pot. Can I can them for shelf storage?','No improvised boiling-water process; appropriate pressure canner/tested recipe.'),
 ('A8','Who in my people records can repair bicycles, and what do they need?','Alex, bicycle repair, needs water.'),
 ('A10','Summarize my situation log, separating what was observed from what was only reported.','Bridge damage Reported by neighbor; clean containers Observed; do not merge certainty.'),
 ('A11','Teach a beginner how to wash hands using stored safe water and soap. One short lesson and a check question.','Practical short lesson; one check question.'),
 ('A12','What does the pump repair project need first, who owns it, and when is its next maintenance check?','Alex; replacement seal and isolated pump; check 2026-09-20.'),
]

def main():
 root=Path(__file__).resolve().parent.parent
 catalog=json.loads((root/'resources/model-catalog.json').read_text())['models']
 model_path=Path(os.environ.get('JARVIS_TEST_MODEL',str(root/'models'/catalog[-1]['filename']))).resolve()
 if not model_path.is_file():raise SystemExit('Finish preparing the model first.')
 with tempfile.TemporaryDirectory(prefix='jarvis-use-cases-') as temp:
  os.environ['JARVISS_DATA']=temp
  from jarviss import planner
  from jarviss.library import import_note
  from jarviss.assistant import messages
  from jarviss.model import LocalModel
  import urllib.request
  original_open=urllib.request.urlopen
  def local_only(request,*args,**kwargs):
   url=request.full_url if isinstance(request,urllib.request.Request) else request
   if not str(url).startswith('http://127.0.0.1:'):raise AssertionError('External request during offline verification')
   return original_open(request,*args,**kwargs)
  urllib.request.urlopen=local_only
  import_note('TrainingPump TP1 manual','TEST FIXTURE. TrainingPump TP1: E04 means intake obstruction. Switch off and check the intake filter. Do not open the electrical housing. Isolate the pump before maintenance.')
  import_note('TrainingBike B1 manual','TEST FIXTURE. TrainingBike B1 punctured tube: remove the wheel following the wheel release instructions. Remove the tire and tube using tire levers. Inspect the tire and remove the puncture cause. Install a correct-size spare tube, seat the tire evenly, inflate to the tire label, reinstall the wheel securely, and check brakes before riding.')
  import_note('TrainingRadio R1 manual','TEST FIXTURE. TrainingRadio R1: select Channel 3 on both units. Hold the TALK button to transmit; release to listen. Test nearby. Do not assume range.')
  records=[('supplies',dict(name='Water',quantity=30,unit='liters',daily=10)),('power',dict(name='Radio',watts=12,hours=2)),('tasks',dict(name='Find safe water',priority='Now',owner='Sam',needs='Clean containers')),('tasks',dict(name='Paint storage shelf',priority='Later')),('tasks',dict(name='Repair pump',priority='Today',owner='Alex',needs='Replacement seal and isolated pump',check='2026-09-20')),('garden',dict(name='Beans',quantity=20,plant_on='2026-05-01',days=60)),('people',dict(name='Alex',skills='Bicycle repair',needs='Water',contact='Library at noon')),('log',dict(name='Bridge damaged',status='Reported',observer='Neighbor')),('log',dict(name='Clean containers ready',status='Observed',observer='Sam'))]
  for kind,record in records:planner.command('planner_save',{'kind':kind,**record})
  planner.command('planner_energy',dict(battery_wh=120,solar_watts=20,sun_hours=3,efficiency=80))
  model=LocalModel();result={'model':model_path.name,'gpu_layers':os.environ.get('JARVIS_TEST_GPU','auto'),'fixture_data':True,'cases':[],'review':'Responses require semantic review; successful generation alone is not a pass.'}
  target=root/'local-data'/os.environ.get('JARVIS_TEST_RESULTS','use-case-results.json')
  try:
   from jarviss.setup import model_catalog
   context=next((m['context'] for m in model_catalog() if m['filename']==model_path.name),8192)
   start=time.monotonic();model.start(model_path,os.environ.get("JARVIS_TEST_GPU","auto"),context=context);result['load_seconds']=round(time.monotonic()-start,2)
   result['context']=context
   print('Model loaded',result['load_seconds'],flush=True)
   import urllib.error
   try:
    urllib.request.urlopen(model.url+'/v1/models')
    raise AssertionError('Local model endpoint accepted an unauthenticated client')
   except urllib.error.HTTPError as error:
    assert error.code==401
    result['private_local_endpoint']=True
   selected=set(filter(None,os.environ.get('JARVIS_TEST_CASES','').split(',')))
   for identifier,question,expected in CASES:
    if selected and identifier not in selected:continue
    start=time.monotonic()
    answer=model.chat(messages({'situation':'Extended outage; phone and internet unavailable.'},[],question),max_tokens=320)
    row=dict(id=identifier,question=question,expected=expected,answer=answer,seconds=round(time.monotonic()-start,2))
    result['cases'].append(row);target.write_text(json.dumps(result,indent=2))
    print(json.dumps(row),flush=True)
  finally:model.close()

if __name__=='__main__':main()
