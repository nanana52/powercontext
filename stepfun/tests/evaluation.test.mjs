import test from 'node:test';
import assert from 'node:assert/strict';
import {median, mean, recallAtK, ndcgAtK} from '../web/evaluation.js';
test('median and average',()=>{assert.equal(median([8,2,10]),8);assert.equal(median([10,2]),6);assert.equal(mean([0,1]),0.5);});
test('real retrieval ranking metrics',()=>{
  assert.equal(recallAtK(['a','c','x'],['a','b'],3),0.5);
  assert.equal(ndcgAtK(['a','b'],['a','b'],3),1);
  assert.ok(ndcgAtK(['b','x','a'],['a','b'],3)<1);
});
