"""Small persistent records and transparent calculations for everyday offline work."""
import math
import threading
import uuid
from datetime import date,datetime,timedelta,timezone
from .storage import DATA,read_json,write_json

SCHEMAS={
 'supplies':{'name':('Item','text',True),'quantity':('Amount left','number',True),'unit':('Unit','text',True),'daily':('Used by the group each day','number',False),'notes':('Notes','text',False)},
 'tasks':{'name':('Task or repair project','text',True),'priority':('Priority','select:Now,Today,Later',True),'owner':('Who','text',False),'due':('Due','date',False),'needs':('Needs first · materials or another task','text',False),'check':('Next maintenance check','date',False),'notes':('Notes','text',False)},
 'power':{'name':('Device','text',True),'watts':('Watts while running','number',True),'hours':('Hours each day','number',True)},
 'garden':{'name':('Crop or seed','text',True),'quantity':('Seeds or plants left','number',False),'plant_on':('Planting date','date',False),'days':('Days to harvest · from seed packet','number',False),'next_check':('Next check','date',False),'notes':('Place, observations or harvest record','text',False)},
 'people':{'name':('Person or group','text',True),'skills':('Skills','text',False),'resources':('Can share','text',False),'needs':('Needs help with','text',False),'responsibility':('Responsible for','text',False),'contact':('Meeting point or radio channel','text',False)},
 'log':{'name':('What happened','text',True),'status':('Status','select:Observed,Reported,Assumption,Decision',True),'place':('Where','text',False),'observer':('Who saw or reported it','text',False),'notes':('Details','text',False)}
}
LOCK=threading.RLock()


def load():
 with LOCK:
  value=read_json(DATA/'planner.json',{})
  return {**{k:[] for k in SCHEMAS},'energy':{},**value}


def field(value,spec):
 label,kind,required=spec
 if value in ('',None):
  if required:raise ValueError(f'Enter {label.lower()}.')
  return ''
 if kind=='number':
  try:n=float(value)
  except (ValueError,TypeError):raise ValueError(f'Enter a number for {label.lower()}.') from None
  if not math.isfinite(n) or not 0<=n<=1e12:raise ValueError(f'{label} must be zero or greater.')
  return n
 text=str(value).strip()
 if len(text)>2000:raise ValueError(f'{label} is too long.')
 if kind=='date':date.fromisoformat(text)
 if kind.startswith('select:') and text not in kind[7:].split(','):raise ValueError(f'Choose {label.lower()}.')
 return text


def command(method,args):
 with LOCK:
  value=load();kind=args.get('kind')
  if method=='planner_energy':
   value['energy']={k:field(args.get(k), (label,'number',True)) for k,label in [('battery_wh','Usable battery watt-hours'),('solar_watts','Solar panel watts'),('sun_hours','Equivalent full-sun hours'),('efficiency','Charging efficiency percent')]}
   if value['energy']['efficiency']>100 or value['energy']['sun_hours']>24:raise ValueError('Use an efficiency from 0 to 100 and sun hours from 0 to 24.')
  elif kind not in SCHEMAS:raise ValueError('Choose a planner section.')
  elif method=='planner_save':
   row={key:field(args.get(key),spec) for key,spec in SCHEMAS[kind].items()}
   if kind=='power' and row['hours']>24:raise ValueError('Daily use cannot exceed 24 hours.')
   if kind=='garden' and row['days']!='':
    if row['days']>36500 or not row['days'].is_integer():raise ValueError('Enter whole days to harvest, up to 36,500.')
    if row['plant_on']:
     try:date.fromisoformat(row['plant_on'])+timedelta(days=row['days'])
     except OverflowError:raise ValueError('The harvest date is outside the supported calendar.') from None
   identifier=str(args.get('id') or uuid.uuid4());old=next((r for r in value[kind] if r['id']==identifier),{})
   if args.get('id') and not old:raise ValueError('This record no longer exists. Refresh and try again.')
   row.update(id=identifier,done=old.get('done',False),created_at=old.get('created_at',datetime.now(timezone.utc).isoformat()))
   value[kind]=[r for r in value[kind] if r['id']!=identifier]+[row]
   if len(value[kind])>1000:raise ValueError('This section has reached 1,000 records.')
  elif method=='planner_done':
   row=next((r for r in value[kind] if r['id']==args.get('id')),None)
   if row is None:raise ValueError('Record not found.')
   row['done']=not row.get('done',False)
  elif method=='planner_delete':value[kind]=[r for r in value[kind] if r['id']!=args.get('id')]
  else:raise ValueError('Unknown planner action.')
  write_json(DATA/'planner.json',value)
  return state()


def state():
 value=load()
 for row in value['supplies']:
  row['days_left']=round(row['quantity']/row['daily'],2) if row.get('daily') else None
 for row in value['garden']:
  try:row['harvest_on']=(date.fromisoformat(row['plant_on'])+timedelta(days=row['days'])).isoformat() if row.get('plant_on') and row.get('days') not in ('',None) else ''
  except (ValueError,OverflowError):row['harvest_on']=''
 value['tasks'].sort(key=lambda r:(r.get('done',False),['Now','Today','Later'].index(r['priority']),r.get('due') or '9999'))
 daily=sum(r['watts']*r['hours'] for r in value['power'])
 energy=value['energy'];solar=energy.get('solar_watts',0)*energy.get('sun_hours',0)*energy.get('efficiency',0)/100
 value['power_summary']={'daily_wh':round(daily,2),'solar_wh':round(solar,2),'shortfall_wh':round(max(0,daily-solar),2),'battery_days':round(energy.get('battery_wh',0)/daily,2) if daily else None}
 return value
