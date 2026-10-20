"""Incremental human review: validate displayed frames, not the whole video per click."""
import copy,hashlib,json
from pathlib import Path
from collections import OrderedDict
from . import dataset as ds

class ReviewStore:
    def __init__(self,profile,root):
        self.root=Path(root);self.profile=profile
        with ds.locked(self.root):
            payload=(self.root/'manifest.json').read_bytes()
            self.data=ds.load(self.root)
        if self.data.get('export'):raise ValueError('Review the original recording dataset, not an exported snapshot.')
        if self.data['classes']!=profile.data['allowed_classes']:raise ValueError('Dataset classes differ from profile')
        self.rows={row['id']:row for row in self.data['frames']}
        if len(self.rows)!=len(self.data['frames']):raise ValueError('Duplicate frame IDs')
        for row in self.rows.values():
            meta=self.data['sessions'][row['session_id']]['casts'][row['cast_id']].get('metadata',{})
            if meta.get('task_id')!=profile.task_id:raise ValueError('Dataset task does not match profile')
        self.digest=hashlib.sha256(payload).hexdigest();self.cache=OrderedDict()
    def image(self,frame_id):
        if frame_id in self.cache:
            self.cache.move_to_end(frame_id);return self.cache[frame_id]
        row=self.rows[frame_id];images={}
        # The complete selected row is validated, including its image checksum and shape.
        ds.validate(self.root,dict(self.data,frames=[row]),images=images)
        image=images[frame_id];image.flags.writeable=False
        self.cache[frame_id]=image
        while len(self.cache)>3:self.cache.popitem(last=False)
        return image
    def save(self,frame_id,boxes,reviewer):
        if not isinstance(reviewer,str) or not reviewer.strip():raise ValueError('Reviewer name required')
        row=self.rows[frame_id]
        ds.boxes_valid(boxes,row['width'],row['height'],self.data['classes'])
        self.image(frame_id)
        with ds.locked(self.root):
            path=self.root/'manifest.json'
            if hashlib.sha256(path.read_bytes()).hexdigest()!=self.digest:
                raise ValueError('Dataset changed in another process. Close and reopen review to avoid overwriting it.')
            if hashlib.sha256(ds.image_path(self.root,row['image']).read_bytes()).hexdigest()!=row['sha256']:
                raise ValueError('Picture changed since recording; review cannot be saved.')
            previous=copy.deepcopy(row['annotation'])
            row['annotation'].update(boxes=copy.deepcopy(boxes),reviewed=True,review_source='human',
                                     reviewer=reviewer.strip(),updated_utc=ds.utc_now())
            try:ds.atomic_json(path,self.data)
            except Exception:
                row['annotation']=previous;raise
            self.digest=hashlib.sha256(path.read_bytes()).hexdigest()
