from pathlib import Path
import hashlib
import json

repo = Path.cwd()
target = repo.parent / 'RSTV4/src/rstv4/catalog_web.html'
out = repo / '.tmp/scholar-catalog-popover-fix-v1'
out.mkdir()
raw = target.read_bytes()
(out / 'catalog_web.html.before.raw').write_bytes(raw)
old = '''          document.querySelector(`[data-panel="${panel}"]`).classList.toggle('active',!el.hidden);
        }
      }
      function displayValue'''
new = '''          document.querySelector(`[data-panel="${panel}"]`).classList.toggle('active',!el.hidden);
        }
        positionCatalogPanels();
      }
      function positionCatalogPanels(){
        const top=document.querySelector('.top').getBoundingClientRect().bottom+window.scrollY+8;
        for(const panel of document.querySelectorAll('.popover:not([hidden])'))panel.style.top=`${top}px`;
      }
      window.addEventListener('resize',positionCatalogPanels);
      function displayValue'''
old_bytes = old.encode('utf-8')
new_bytes = new.encode('utf-8')
if b'\r\n' in raw:
    old_bytes = old_bytes.replace(b'\n', b'\r\n')
    new_bytes = new_bytes.replace(b'\n', b'\r\n')
assert raw.count(old_bytes) == 1
after = raw.replace(old_bytes, new_bytes)
target.write_bytes(after)
assert after.replace(new_bytes, old_bytes) == raw
receipt = {'target':str(target),'before_sha256':hashlib.sha256(raw).hexdigest(),
           'after_sha256':hashlib.sha256(after).hexdigest(), 'old':old,'new':new,
           'crlf':b'\r\n' in raw,'reason':'Actual native Sort panel at y47 covered toolbar y62..91.5; position every open panel below actual toolbar and recalculate on resize.',
           'queries_or_business_rules_changed':False}
(out / 'repair.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'old','new'}}))
