def congress_demo():
    reports=[];records=[]
    for year in [2024,2025]:
        rid=f'DEMO-house-{year}'
        candidates=[]
        for i,(name,ticker,low,high)in enumerate([('DEMO Technology [ST]','DEMO',100001,250000),('DEMO Energy [ST]','DEMO2',15001,50000)]):
            c={'id':rid+'-'+str(i),'report_id':rid,'source_sha256':'DEMO','page':1,'kind':'asset','asset':name,'ticker':ticker,'owner':'SP','transaction_type':'','transaction_date':'','amount_min':low if year==2024 else low*2,'amount_max':high if year==2024 else high*2,'valuation_date':f'{year}-12-31','valuation_basis':'Fictional year-end value','reviewer':'DEMO reviewer','reviewed_at':'2026-10-06','notes':'Fictional','amount_text':f'${low:,} - ${high:,}','method':'ocr','mean_word_confidence':88.5,'excerpt':f'FICTIONAL EXAMPLE: {name} SP ${low:,} - ${high:,}','review_status':'needs_review'}
            candidates.append(c)
            records.append({**c,'person':'DEMO Legislator','jurisdiction':'DEMO House','report_type':'Annual','filed_date':f'{year+1}-05-15','source_url':'','review_status':'reviewed'})
        reports.append({'report_id':rid,'person':'DEMO Legislator','jurisdiction':'DEMO House','report_type':'Annual','filed_date':f'{year+1}-05-15','source_url':'','source_sha256':'DEMO','page_count':1,'candidates':candidates,'status':'demo','stale':False})
    return {'reports':reports,'records':records,'coverage_note':'Fictional demonstration only'}
