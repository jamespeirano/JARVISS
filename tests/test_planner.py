import itertools,json,socket,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from jarviss import planner
from jarviss.local_board import LocalBoard
from jarviss.location_search import LocationIndex,state_boundaries,in_state
from jarviss.assistant import relevant_guides,messages
from jarviss.map_questions import answer_map
from jarviss.library import import_text,retrieve
import urllib.request,urllib.error

class PlannerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.patches=[patch('jarviss.planner.DATA',self.root),patch('jarviss.local_board.DATA',self.root),patch('jarviss.library.DATA',self.root)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def test_supplies_power_garden_and_priority_persist(self):
  p=planner.command('planner_save',{'kind':'supplies','name':'Water','quantity':30,'unit':'liters','daily':10})
  self.assertEqual(p['supplies'][0]['days_left'],3)
  planner.command('planner_save',{'kind':'power','name':'Radio','watts':12,'hours':2})
  p=planner.command('planner_energy',{'battery_wh':120,'solar_watts':20,'sun_hours':3,'efficiency':80})
  self.assertEqual(p['power_summary'],{'daily_wh':24,'solar_wh':48,'shortfall_wh':0,'battery_days':5})
  planner.command('planner_save',{'kind':'tasks','name':'Paint','priority':'Later'})
  planner.command('planner_save',{'kind':'tasks','name':'Find water','priority':'Now','owner':'Alex','needs':'Containers'})
  p=planner.command('planner_save',{'kind':'garden','name':'Beans','plant_on':'2026-05-01','days':60})
  self.assertEqual(p['garden'][0]['harvest_on'],'2026-06-30')
  self.assertEqual(p['tasks'][0]['name'],'Find water')
  self.assertTrue((self.root/'planner.json').exists())
  planner.command('planner_done',{'kind':'tasks','id':p['tasks'][0]['id']})
  self.assertEqual(planner.state()['tasks'][-1]['name'],'Find water')
 def test_records_reject_invalid_numbers_and_never_change_medication_doses(self):
  for v in [-1,'nan','inf']:
   with self.assertRaises(ValueError):planner.command('planner_save',{'kind':'supplies','name':'Food','quantity':v,'unit':'cans'})
  with self.assertRaises(ValueError):planner.command('planner_save',{'kind':'power','name':'Radio','watts':5,'hours':25})
  p=planner.command('planner_save',{'kind':'supplies','name':'Prescribed tablets','quantity':10,'unit':'tablets','daily':2})
  self.assertEqual(p['supplies'][0]['daily'],2);self.assertEqual(p['supplies'][0]['days_left'],5)
 def test_people_and_fact_status_reach_chat(self):
  planner.command('planner_save',{'kind':'people','name':'Alex','skills':'Bicycle repair','needs':'Water'})
  planner.command('planner_save',{'kind':'log','name':'Bridge damaged','status':'Reported','observer':'Neighbor'})
  value=messages({},[],'Summarize people and reports')[0]['content']
  self.assertIn('Bicycle repair',value);self.assertIn('Reported',value)
 def test_garden_invalid_dates_cannot_poison_saved_records(self):
  for days in (1e12,1.5):
   with self.assertRaises(ValueError):planner.command('planner_save',{'kind':'garden','name':'Beans','plant_on':'2026-05-01','days':days})
  with self.assertRaises(ValueError):planner.command('planner_save',{'kind':'garden','name':'Beans','plant_on':'9999-12-31','days':60})
  self.assertEqual(planner.state()['garden'],[])
  p=planner.command('planner_save',{'kind':'garden','name':'Ready crop','plant_on':'2026-05-01','days':0})
  self.assertEqual(p['garden'][0]['harvest_on'],'2026-05-01')
 def test_manual_retrieval_and_pdf_import(self):
  p=self.root/'TrainingPump.txt';p.write_text('TrainingPump TP1 manual. E04 means intake obstruction. Switch off and check the intake filter. Do not open the electrical housing.')
  import_text(p);result=retrieve('TrainingPump E04 intake')
  self.assertEqual(result[0]['title'],'TrainingPump.txt');self.assertIn('intake obstruction',result[0]['text'])
  from pypdf import PdfWriter
  from pypdf.generic import DictionaryObject,NameObject,NumberObject,DecodedStreamObject
  writer=PdfWriter();page=writer.add_blank_page(400,500)
  font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
  page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
  stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 450 Td (TrainingRadio R1. Channel 3. Hold talk to transmit. Release to listen.) Tj ET')
  page[NameObject('/Contents')]=writer._add_object(stream)
  pdf=self.root/'TrainingRadio.pdf';writer.write(pdf);import_text(pdf)
  self.assertIn('Hold talk',retrieve('TrainingRadio channel')[0]['text'])
 def test_short_model_and_fault_codes_select_the_correct_manual(self):
  manuals=[{'title':f'Radio R{i} manual','imported_at':'fixture','text':f'Radio R{i}. E1 means test condition {i}.'} for i in [2,3,4,5,1]]
  self.assertEqual(retrieve('Radio R1 E1',manuals)[0]['title'],'Radio R1 manual')
  self.assertEqual(retrieve('My UnknownGenerator ZX99 shows E1. What does it mean?',manuals),[])
 def test_non_map_use_cases_do_not_trigger_navigation(self):
  for q in ['How do we find each other?','Find the generator manual','Translate this warning label','Where can I find repair instructions?','Which task matters first?']:
   self.assertIsNone(answer_map(q,{},None),q)
 def test_all_short_guides_have_useful_prompts(self):
  from jarviss.assistant import GUIDES
  self.assertGreaterEqual(len(GUIDES),16)
  for g in GUIDES:
   self.assertLessEqual(len(g['text'].split()),100);self.assertTrue(g['prompt'])
  self.assertEqual(relevant_guides('generator warning code')[0]['id'],'equipment')
  self.assertEqual(relevant_guides('Translate a label')[0]['id'],'learn')

class BoardTests(unittest.TestCase):
 def test_board_off_by_default_and_network_failure_is_actionable(self):
  board=LocalBoard()
  with patch('jarviss.local_board.socket.gethostbyname_ex',side_effect=OSError('No host')):
   with self.assertRaisesRegex(ValueError,'local Wi-Fi or Ethernet'):board.start()
  self.assertFalse(board.state()['active'])
 def test_two_local_clients_exchange_messages_with_code_and_restart_persistence(self):
  with tempfile.TemporaryDirectory() as temp,patch('jarviss.local_board.DATA',Path(temp)):
   board=LocalBoard()
   try:
    state=board.start('127.0.0.1');url=state['address']+'/messages'
    with self.assertRaises(urllib.error.HTTPError) as failure:urllib.request.urlopen(url)
    self.assertEqual(failure.exception.code,401)
    bad=urllib.request.Request(url,data=b'[]',headers={'X-Board-Code':state['code']})
    with self.assertRaises(urllib.error.HTTPError) as failure:urllib.request.urlopen(bad)
    self.assertEqual(failure.exception.code,400)
    with self.assertRaises(urllib.error.HTTPError) as failure:urllib.request.urlopen(state['address']+'/planner.json')
    self.assertEqual(failure.exception.code,404)
    for name,text in [('Alex','Meet at the library at noon.'),('Sam','Received. Bringing water.')]:
     req=urllib.request.Request(url,data=json.dumps({'name':name,'text':text}).encode(),headers={'X-Board-Code':state['code'],'Content-Type':'application/json'})
     with urllib.request.urlopen(req) as response:self.assertTrue(json.load(response)['saved'])
     time.sleep(1.05)  # One address may post once a second.
    with urllib.request.urlopen(urllib.request.Request(url,headers={'X-Board-Code':state['code']})) as response:self.assertEqual(len(json.load(response)),2)
    board.close();self.assertFalse(board.state()['active']);self.assertEqual(len(LocalBoard().state()['messages']),2)
   finally:board.close()


 def test_peers_are_rate_limited_and_input_is_type_checked(self):
  with tempfile.TemporaryDirectory() as temp,patch('jarviss.local_board.DATA',Path(temp)):
   board=LocalBoard()
   try:
    state=board.start('127.0.0.1');url=state['address']+'/messages'
    def post(body,code=state['code']):
     req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'X-Board-Code':code,'Content-Type':'application/json'})
     try:
      with urllib.request.urlopen(req) as response:return response.status,json.load(response)
     except urllib.error.HTTPError as failure:return failure.code,json.load(failure)
    self.assertEqual(post({'name':'Alex','text':'First'})[0],200)
    status,result=post({'name':'Alex','text':'Second'})
    self.assertEqual(status,429);self.assertIn('Wait a second',result['error'])
    self.assertEqual(post({'name':{'a':1},'text':'Third'})[0],400)
    self.assertEqual(post({'name':'Alex','text':'Wrong code'},code='C\xd6DE')[0],401)
    board.add('Jarvis','Own posts are not limited.');board.add('Jarvis','Second own post.')
    self.assertEqual([m['text'] for m in board.state()['messages']],['First','Own posts are not limited.','Second own post.'])
    time.sleep(1.05)
    self.assertEqual(post({'name':'Alex','text':'Later'})[0],200)
   finally:board.close()
 def test_a_flooding_peer_only_evicts_its_own_history(self):
  with tempfile.TemporaryDirectory() as temp,patch('jarviss.local_board.DATA',Path(temp)),patch('jarviss.local_board.time.monotonic',side_effect=itertools.count(step=2)):
   board=LocalBoard()
   for i in range(5):board.add('Sam',f'B {i}','192.168.1.5')
   for i in range(3):board.add('Jarvis',f'Own {i}')
   for i in range(1200):board.add('Alex',f'A {i}','192.168.1.7')
   rows=json.loads((Path(temp)/'local-messages.json').read_text(encoding='utf-8'))
   self.assertEqual(len(rows),1000)
   self.assertEqual([r['text'] for r in rows if r['from']!='192.168.1.7'],[f'B {i}' for i in range(5)]+[f'Own {i}' for i in range(3)])
   self.assertEqual([r['from'] for r in rows[:8]],['192.168.1.5']*5+['local']*3)
   self.assertEqual(rows[-1]['text'],'A 1199');self.assertEqual(rows[8]['text'],'A 208')
   self.assertTrue(all('from' not in m for m in board.state()['messages']))  # Addresses stay off the board page.
 def test_saturated_board_replies_busy_and_recovers(self):
  with tempfile.TemporaryDirectory() as temp,patch('jarviss.local_board.DATA',Path(temp)):
   board=LocalBoard();board.concurrency=1
   try:
    state=board.start('127.0.0.1');host,port=state['address'][7:].rsplit(':',1)
    stuck=socket.create_connection((host,int(port)));stuck.sendall(b'GET / HTTP/1.0\r\nX-Half: open')  # never completes its request
    with self.assertRaises(urllib.error.HTTPError) as failure:urllib.request.urlopen(state['address']+'/')
    self.assertEqual(failure.exception.code,503);self.assertIn('busy',json.load(failure.exception)['error'])
    stuck.close()
    with urllib.request.urlopen(state['address']+'/') as response:self.assertIn(b'Group messages',response.read())
   finally:board.close()
 def test_punctuation_only_search_matches_nothing(self):
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as temp:
   file=Path(temp)/'map';file.write_text('fixture')
   index=LocationIndex(SimpleNamespace(path=file),Path(temp))
   index.records=[{'name':'Springfield','kind':'city','abbreviation':'','population':100,'point':[39.8,-89.65]}]
   for query in ('...','?!','.., IL',' , '):self.assertEqual(index.search(query),[])
   self.assertEqual(len(index.search('Spring')),1)


class ContextEdgeTests(unittest.TestCase):
 def test_new_stock_omits_old_estimates_without_changing_saved_records(self):
  from jarviss.assistant import planning_context
  with tempfile.TemporaryDirectory() as temp,patch('jarviss.planner.DATA',Path(temp)):
   planner.command('planner_save',{'kind':'supplies','name':'Water','quantity':30,'unit':'liters','daily':10})
   planner.command('planner_save',{'kind':'tasks','name':'Find water','priority':'Now'})
   context=planning_context('We have six liters of safe water and a low battery. Which task matters first?')
   self.assertNotIn('supplies',context);self.assertNotIn('supply_summary',context);self.assertNotIn('power_summary',context)
   self.assertEqual(context['tasks'][0]['name'],'Find water')
   self.assertEqual(planner.state()['supplies'][0]['quantity'],30)
   self.assertNotIn('supplies',planning_context('Is this diesel-smelling stream usable if I boil it?'))
 def test_inventory_summary_includes_critical_item_after_first_six(self):
  from jarviss.assistant import planning_context
  with tempfile.TemporaryDirectory() as temp,patch('jarviss.planner.DATA',Path(temp)):
   for i in range(10):planner.command('planner_save',{'kind':'supplies','name':f'Supply {i}','quantity':100,'unit':'units','daily':1})
   planner.command('planner_save',{'kind':'supplies','name':'Water','quantity':5,'unit':'liters','daily':10})
   context=planning_context('What will run out first?')
   self.assertEqual(context['supply_summary']['total_items'],11)
   self.assertEqual(context['supply_summary']['runs_out_first'][0],{'name':'Water','days_left':.5})
   self.assertEqual(context['supplies'][0]['name'],'Water')
 def test_state_filter_disambiguates_duplicate_city_names(self):
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as temp:
   file=Path(temp)/'map';file.write_text('fixture')
   index=LocationIndex(SimpleNamespace(path=file),Path(temp))
   index.records=[{'name':'Springfield','kind':'city','abbreviation':'','population':100,'point':[39.8,-89.65]}, {'name':'Springfield','kind':'city','abbreviation':'','population':200,'point':[42.1,-72.59]}]
   found=index.search('Springfield, IL')
   self.assertEqual(len(found),1);self.assertEqual(found[0]['state_code'],'IL')
   found=index.search('Springfield, Massachusetts')
   self.assertEqual(len(found),1);self.assertEqual(found[0]['state_code'],'MA')
   self.assertEqual(index.search('Springfield, Unknown'),[])
   self.assertEqual(index.address_parts('Springfield, IL'),{'city':'Springfield, IL','street':''})
   self.assertEqual(index.address_parts('12 Main Street Springfield IL 62701'),{'city':'Springfield, IL','street':'12 Main Street'})
   self.assertEqual(index.address_parts('12 Main Street, Springfield, Illinois'),{'city':'Springfield, Illinois','street':'12 Main Street'})

if __name__=='__main__':unittest.main()
